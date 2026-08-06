from __future__ import annotations

import csv
import glob
import math
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .grid import fault_impedance_ohm, impedance_from_fault_level, infinite_bus_voltage
from .models import Event, PlaybackPoint, Scenario


class PsseError(RuntimeError):
    pass


class PsseBackend:
    def __init__(self, psspy, config, hooks=None):
        self.psspy = psspy
        self.config = config
        self.hooks = hooks
        self._i = psspy.getdefaultint()
        self._f = psspy.getdefaultreal()
        self._s = psspy.getdefaultchar()
        self.current_fault_number = 1
        self.steps_per_write = int(config.section("dynamics").get("nplt", 0))

    def _check(self, result, action: str):
        ierr = result[0] if isinstance(result, tuple) else result
        if isinstance(ierr, int) and ierr != 0:
            raise PsseError("{} failed with PSS/E error {}".format(action, ierr))
        return result[1] if isinstance(result, tuple) and len(result) > 1 else result

    @property
    def system(self) -> Dict[str, Any]:
        return self.config.section("system")

    def _configure_native_output(self, log_stem: Path) -> str:
        """Route PSS/E's own report/progress streams to console, files or quiet.

        ``console`` keeps the same transparent PowerShell behaviour as the
        company runner: load-flow iterations, tap/machine changes, dynamic
        initialisation and RUN progress remain visible. ``files`` preserves
        those streams beside the runtime log stem, while ``quiet`` suppresses
        them for unattended batches.
        """
        configured = self.config.data.get("psse_output_mode")
        if configured in (None, ""):
            configured = "files" if bool(self.config.data.get("keep_psse_logs", False)) else "quiet"
        mode = str(configured).strip().lower()
        aliases = {
            "console": "console",
            "screen": "console",
            "files": "files",
            "file": "files",
            "quiet": "quiet",
            "off": "quiet",
            "none": "quiet",
        }
        if mode not in aliases:
            raise ValueError(
                "psse_output_mode must be console, files or quiet; got {!r}".format(configured)
            )
        mode = aliases[mode]
        selector = {"console": 1, "files": 2, "quiet": 6}[mode]
        suffixes = {
            "report_output": "_report.log",
            "progress_output": "_progress.log",
            "alert_output": "_alert.log",
            "prompt_output": "_prompt.log",
        }
        for method_name, suffix in suffixes.items():
            method = getattr(self.psspy, method_name, None)
            if method is None:
                continue
            target = str(log_stem) + suffix if mode == "files" else ""
            self._check(method(selector, target, [0, 0]), "configure {}".format(method_name))
        return mode

    def initialize(self, sav_path: Path, log_stem: Path, solve_load_flow: bool = True) -> None:
        buses = int(self.config.section("psse").get("max_buses", 200000))
        self._check(self.psspy.psseinit(buses), "psseinit")
        self._configure_native_output(log_stem)
        self._check(self.psspy.case(str(sav_path)), "load SAV")
        if solve_load_flow:
            self.solve_load_flow()

    def save_case(self, sav_path: Path) -> None:
        Path(sav_path).parent.mkdir(parents=True, exist_ok=True)
        self._check(self.psspy.save(str(sav_path)), "save dispatched SAV")

    def solve_load_flow(self, repetitions: Optional[int] = None) -> None:
        count = int(repetitions or self.config.section("load_flow").get("solve_repetitions", 2))
        for _ in range(max(1, count)):
            self._check(self.psspy.fnsl([0, 0, 0, 1, 1, 0, 0, 0]), "load flow")

    def resolve_bus(self, value: Any) -> int:
        if isinstance(value, (int, float)):
            return int(value)
        aliases = self.system.get("bus_aliases", {})
        if str(value) in aliases:
            return int(aliases[str(value)])
        if str(value).lower() == "poc":
            return int(self.system["poc_bus"])
        if str(value).lower() == "fault":
            return int(self.system.get("fault_bus", self.system["poc_bus"]))
        try:
            return int(str(value))
        except ValueError:
            raise PsseError("Unknown bus alias {!r}; add it to system.bus_aliases".format(value))

    def branch(self, alias: str = "grid") -> Dict[str, Any]:
        branches = self.system.get("branches", {})
        if alias in branches:
            return branches[alias]
        if alias == "grid":
            return self.system["grid_branch"]
        raise PsseError("Unknown branch alias {!r}".format(alias))

    def set_branch_impedance(self, branch: Dict[str, Any], r_pu: float, x_pu: float) -> None:
        result = self.psspy.branch_chng_3(
            int(branch["from_bus"]), int(branch["to_bus"]), str(branch.get("id", "1")),
            [self._i] * 6, [float(r_pu), float(x_pu)] + [self._f] * 10, [self._f] * 12, self._s,
        )
        self._check(result, "change branch impedance")

    def configure_grid(self, scenario: Scenario) -> Tuple[float, float]:
        fault_level = scenario.get("Grid_FL_MVA_sig")
        if fault_level in (None, ""):
            scr = scenario.get("Grid_SCR")
            base = scenario.get("Pbase_MW", self.config.section("bases").get("p_mw"))
            if scr in (None, "") or base in (None, ""):
                raise PsseError("Scenario has neither Grid_FL_MVA_sig nor Grid_SCR + plant base")
            fault_level = float(scr) * float(base)
        xr = float(scenario.get("Grid_X2R_sig"))
        r_pu, x_pu = impedance_from_fault_level(float(fault_level), xr)
        self.set_branch_impedance(self.branch("grid"), r_pu, x_pu)
        return r_pu, x_pu

    def _target_power(self, scenario: Scenario) -> Tuple[float, float]:
        bases = self.config.section("bases")
        p = scenario.get("Ppoc_MW_sig")
        if p in (None, ""):
            p = float(scenario.get("Ppoc_pu", 0.0)) * float(bases["p_mw"])
        q = scenario.get("Qpoc_MVAr_init")
        if q in (None, ""):
            q = float(scenario.get("Qpoc_pu", 0.0)) * float(bases.get("q_mvar", bases["p_mw"]))
        return float(p), float(q)

    def dispatch(self, scenario: Scenario, r_pu: float, x_pu: float) -> None:
        generators = self.system.get("generators", [])
        if not generators:
            raise PsseError("system.generators is empty")
        p_target, q_target = self._target_power(scenario)
        measurement = self.system.get("measurement_branch", self.system["grid_branch"])
        poc = int(measurement["from_bus"])
        infinite = int(measurement["to_bus"])
        ckt = str(measurement.get("id", "1"))
        v_poc = float(scenario.get("Vpoc_pu_sig", self.config.section("bases").get("normal_v_pu", 1.0)))

        # Match the transparent calculation in the supplied open DMAT script:
        # solve the required infinite-bus schedule first, then compensate plant
        # dispatch for the actual network losses measured at the meter branch.
        voltage = infinite_bus_voltage(v_poc, p_target, q_target, r_pu, x_pu)
        self._check(self.psspy.plant_data(int(self.system["infinite_bus"]), [self._i], [voltage, self._f]), "set infinite bus voltage")

        load_flow = self.config.section("load_flow")
        p_tolerance = float(load_flow.get("p_tolerance_mw", load_flow.get("tolerance_mw_mvar", 0.01)))
        q_tolerance = float(load_flow.get("q_tolerance_mvar", load_flow.get("tolerance_mw_mvar", 0.01)))
        max_iterations = int(self.config.section("load_flow").get("max_iterations", 80))
        gain = float(self.config.section("load_flow").get("correction_gain", 1.0))
        for iteration in range(max_iterations):
            self.solve_load_flow(1)
            measured_p = float(self._check(self.psspy.brnmsc(poc, infinite, ckt, "P"), "measure P at POC"))
            measured_q = float(self._check(self.psspy.brnmsc(poc, infinite, ckt, "Q"), "measure Q at POC"))
            p_error, q_error = p_target - measured_p, q_target - measured_q
            if abs(p_error) <= p_tolerance and abs(q_error) <= q_tolerance:
                break
            for generator in generators:
                bus, mac_id = int(generator["bus"]), str(generator.get("id", "1"))
                p_now = float(self._check(self.psspy.macdat(bus, mac_id, "P"), "read generator P"))
                q_now = float(self._check(self.psspy.macdat(bus, mac_id, "Q"), "read generator Q"))
                p_new = p_now + gain * p_error * float(generator.get("p_weight", 0.0))
                q_new = q_now + gain * q_error * float(generator.get("q_weight", 0.0))
                p_new = min(float(generator.get("pmax_mw", p_new)), max(float(generator.get("pmin_mw", p_new)), p_new))
                q_new = min(float(generator.get("qmax_mvar", q_new)), max(float(generator.get("qmin_mvar", q_new)), q_new))
                self._check(
                    self.psspy.machine_data_2(
                        bus, mac_id, [self._i] * 6,
                        # Clamp to the initdef capability first, then temporarily
                        # pin QT/QB to QG. This is the public-API technique used
                        # by the supplied open DMAT load-flow loop to make QG a
                        # dispatch variable instead of a PV-bus outcome.
                        [p_new, q_new, q_new, q_new] + [self._f] * 13,
                    ),
                    "dispatch generator",
                )
        else:
            raise PsseError(
                "Dispatch did not converge after {} iterations (last errors P={:.6g} MW, Q={:.6g} MVAr)".format(
                    max_iterations, p_error, q_error
                )
            )
        self.solve_load_flow(3)

    def configure_scenario_options(self, scenario: Scenario) -> None:
        value = scenario.get("Steps_per_write", scenario.get("Steps_Per_Write", None))
        if value not in (None, ""):
            self.steps_per_write = int(float(value))
        else:
            self.steps_per_write = int(self.config.section("dynamics").get("nplt", 0))

    def make_grid_infinite(self) -> None:
        """Apply the former Pallet post-initialisation callback transparently."""
        self.set_branch_impedance(self.branch("grid"), 0.0, 0.000001)
        poc = int(self.system["poc_bus"])
        infinite = int(self.system["infinite_bus"])
        poc_voltage = float(self._check(self.psspy.busdat(poc, "PU"), "read POC voltage"))
        self._check(self.psspy.plant_data(infinite, [self._i], [poc_voltage, self._f]), "set infinite-grid slack voltage")
        for generator in self.system.get("generators", []):
            bus = int(generator["bus"])
            bus_voltage = float(self._check(self.psspy.busdat(bus, "PU"), "read generator bus voltage"))
            # Local voltage regulation reproduces the intent of setting IREG to
            # the machine bus and VSCHED to the already-solved bus voltage.
            self._check(self.psspy.plant_data(bus, [bus], [bus_voltage, self._f]), "lock generator voltage schedule")
        self.solve_load_flow(3)

    def _write_playback(self, work_dir: Path, points: Iterable[PlaybackPoint]) -> Tuple[Path, Path]:
        settings = self.config.section("playback")
        stem = str(settings.get("file_stem", "playback"))
        plb_path = work_dir / (stem + ".plb")
        dyr_path = work_dir / (stem + ".dyr")
        infinite = int(self.system["infinite_bus"])
        machine_id = str(self.system["infinite_machine"].get("id", "1"))
        initial_voltage = float(self._check(self.psspy.busdat(infinite, "PU"), "read infinite bus voltage"))
        nominal_frequency = float(self.config.section("dynamics").get("frequency_hz", 50.0))
        last_voltage = initial_voltage
        last_frequency = nominal_frequency
        with open(plb_path, "w", encoding="ascii", newline="\n") as stream:
            for point in points:
                voltage = initial_voltage if point.voltage_pu is None else float(point.voltage_pu)
                frequency = nominal_frequency if point.frequency_hz is None else float(point.frequency_hz)
                stream.write("{:.9g} {:.9g} {:.9g}\n".format(point.time, voltage, frequency))
                last_voltage, last_frequency = voltage, frequency
            stream.write("99999 {:.9g} {:.9g}\n".format(last_voltage, last_frequency))
        record = "{}, 'USRMDL', {}, 'PLBVFU1', 1, 1, 3, 4, 3, 6, 1, 1, '{}', 1.0, {:.9g}, 0.000, 0.000 /\n".format(
            infinite, int(machine_id), stem, nominal_frequency
        )
        with open(dyr_path, "w", encoding="ascii", newline="\n") as stream:
            stream.write(record)
        return plb_path, dyr_path

    def initialize_dynamics(self, work_dir: Path, dyr_path: Path, out_path: Path, playback: List[PlaybackPoint]) -> None:
        self._check(self.psspy.cong(0), "convert generators")
        for stage in (1, 2, 3):
            self._check(self.psspy.conl(0, 1, stage, [0, 0], [100.0, 0.0, 0.0, 100.0]), "convert loads stage {}".format(stage))
        self._check(self.psspy.ordr(0), "order network")
        self._check(self.psspy.fact(), "factor network")
        self._check(self.psspy.tysl(0), "switch network")
        for dll in glob.glob(str(work_dir / "*.dll")):
            self._check(self.psspy.addmodellibrary(dll), "load model library {}".format(dll))
        self._check(self.psspy.dyre_new([1, 1, 1, 1], str(dyr_path)), "load DYR")

        if playback:
            _plb_path, playback_dyr = self._write_playback(work_dir, playback)
            infinite = int(self.system["infinite_bus"])
            machine_id = str(self.system["infinite_machine"].get("id", "1"))
            self._check(self.psspy.plmod_remove(infinite, machine_id, 1), "remove infinite machine dynamic model")
            self._check(self.psspy.dyre_add([], str(playback_dyr)), "add playback model")

        dynamics = self.config.section("dynamics")
        self._check(self.psspy.dynamics_solution_param_2(
            intgar1=int(dynamics.get("iterations", 200)),
            realar1=float(dynamics.get("acceleration", 0.2)),
            realar2=float(dynamics.get("tolerance", 0.0001)),
            realar3=float(dynamics.get("time_step_s", 0.001)),
            realar4=float(dynamics.get("frequency_filter_s", 0.02)),
            realar5=float(dynamics.get("time_step_s", 0.001)),
        ), "set dynamic solution parameters")
        self._check(self.psspy.set_chnfil_type(0), "set OUT channel format")
        # set_netfrq is an enable/disable switch, not the nominal frequency in Hz.
        # The wrapped runner explicitly disabled network frequency dependence.
        netfrq = 1 if bool(dynamics.get("frequency_dependence", False)) else 0
        self._check(self.psspy.set_netfrq(netfrq), "set network frequency dependence")
        self.add_channels()
        self._check(self.psspy.strt(outfile=str(out_path)), "start dynamics")
        status = self.psspy.okstrt()
        if status not in (0,):
            raise PsseError("Dynamic initialization failed; okstrt returned {}".format(status))

    def add_channels(self) -> None:
        definition = self.config.section("channel_definition")
        if definition:
            self._add_definition_channels(definition)
            return
        channels = self.config.section("channels")
        poc, infinite = int(self.system["poc_bus"]), int(self.system["infinite_bus"])
        branch = self.system["grid_branch"]
        ckt = str(branch.get("id", "1"))
        self.psspy.voltage_and_angle_channel([-1, -1, -1, poc], ["POC_VOLTAGE", "POC_ANGLE"])
        self.psspy.bus_frequency_channel([-1, poc], "POC_FREQUENCY")
        self.psspy.branch_p_and_q_channel([-1, -1, -1, poc, infinite], ckt, ["POC_P", "POC_Q"])
        self.psspy.voltage_and_angle_channel([-1, -1, -1, infinite], ["GRID_VOLTAGE", "GRID_ANGLE"])
        self.psspy.bus_frequency_channel([-1, infinite], "GRID_FREQUENCY")
        for item in channels.get("buses", []):
            bus, name = int(item["bus"]), str(item["name"])
            self.psspy.voltage_and_angle_channel([-1, -1, -1, bus], [name + "_VOLTAGE", name + "_ANGLE"])
            self.psspy.bus_frequency_channel([-1, bus], name + "_FREQUENCY")
        for item in channels.get("branches", []):
            self.psspy.branch_p_and_q_channel([-1, -1, -1, int(item["from_bus"]), int(item["to_bus"])], str(item.get("id", "1")), [str(item["name"]) + "_P", str(item["name"]) + "_Q"])
        for item in channels.get("models", []):
            base = self.model_index(str(item["model"]), str(item.get("item", "VAR")))
            kind = str(item.get("item", "VAR")).upper()
            for index in item.get("indices", []):
                label = "{}_{}({}+{})".format(item["model"], kind, "L" if kind == "VAR" else "K", index)
                if kind == "VAR":
                    self.psspy.var_channel([-1, base + int(index)], label)
                elif kind == "STATE":
                    self.psspy.state_channel([-1, base + int(index)], label)

    def _model_index_from_definition(self, model: Dict[str, Any], item: str) -> int:
        model_type = str(model.get("model_type", "")).upper()
        if model_type == "OTHER_BUS":
            result = self.psspy.cctmind_buso(
                int(model["bus"]), str(model["registered_name"]), str(item).upper()
            )
        elif model_type == "PLANT":
            result = self.psspy.mdlind(
                int(model["bus"]),
                str(model.get("machine_id", model.get("mach_id", "1"))),
                str(model.get("slot", "GEN")),
                str(item).upper(),
            )
        else:
            raise PsseError("Unsupported chandef model_type {!r}".format(model_type))
        return int(self._check(result, "locate chandef {} model".format(model_type)))

    def _add_definition_channels(self, definition: Dict[str, Any]) -> None:
        """Reproduce HBESS.chandef one-for-one using public psspy calls."""
        for item in definition.get("bus_voltage_channels", []):
            self._check(
                self.psspy.voltage_and_angle_channel(
                    [-1, -1, -1, int(item["bus"])],
                    [str(item["vol_name"]), str(item["ang_name"])],
                ),
                "add voltage channel {}".format(item["vol_name"]),
            )
        for item in definition.get("branch_pq_channels", []):
            branch = item["branch"]
            self._check(
                self.psspy.branch_p_and_q_channel(
                    [-1, -1, -1, int(branch["from_bus"]), int(branch["to_bus"])],
                    str(branch.get("circuit_id", branch.get("id", "1"))),
                    [str(item["p_name"]), str(item["q_name"])],
                ),
                "add branch channels {}/{}".format(item["p_name"], item["q_name"]),
            )
        for kind, key, method_name in (
            ("VAR", "var_channels", "var_channel"),
            ("STATE", "state_channels", "state_channel"),
        ):
            method = getattr(self.psspy, method_name)
            for item in definition.get(key, []):
                base = self._model_index_from_definition(item["model"], kind)
                self._check(
                    method([-1, base + int(item["index"])], str(item["signal_name"])),
                    "add {} channel {}".format(kind, item["signal_name"]),
                )
        quantity_codes = {
            "ANGLE": 1,
            "PELEC": 2,
            "QELEC": 3,
            "ETERM": 4,
            "EFD": 5,
            "PMECH": 6,
            "SPEED": 7,
        }
        for item in definition.get("machine_channels", []):
            machine = item["machine"]
            quantity = str(item["machine_quantity"]).upper()
            if quantity not in quantity_codes:
                raise PsseError("Unsupported chandef machine quantity {!r}".format(quantity))
            self._check(
                self.psspy.machine_array_channel(
                    [-1, quantity_codes[quantity], int(machine["bus"])],
                    str(machine.get("mach_id", machine.get("id", "1"))),
                    str(item["signal_name"]),
                ),
                "add machine channel {}".format(item["signal_name"]),
            )
        for item in definition.get("freq_channels", []):
            bus_value = item["bus"]
            bus = int(bus_value["num"] if isinstance(bus_value, dict) else bus_value)
            self._check(
                self.psspy.bus_frequency_channel([-1, bus], str(item["signal_name"])),
                "add frequency channel {}".format(item["signal_name"]),
            )

    def model_index(self, alias: str, item: str) -> int:
        model = self.config.section("models").get(alias)
        if not model:
            raise PsseError("Unknown model alias {!r}; configure it in models".format(alias))
        method = str(model["method"])
        if method == "mdlind":
            result = self.psspy.mdlind(int(model["bus"]), str(model.get("id", "1")), str(model["class"]), item)
        elif method == "windmind":
            result = self.psspy.windmind(int(model["bus"]), str(model.get("id", "1")), str(model["class"]), item)
        elif method == "cctmind_buso":
            result = self.psspy.cctmind_buso(int(model["bus"]), str(model["name"]), item)
        elif method == "cctmind_mcno":
            result = self.psspy.cctmind_mcno(int(model["bus"]), str(model.get("id", "1")), str(model["name"]), item)
        elif method == "cctmind_msco":
            result = self.psspy.cctmind_msco(int(model["instance"]), item)
        else:
            raise PsseError("Unsupported model lookup method {!r}".format(method))
        return int(self._check(result, "locate model {}".format(alias)))

    def apply_model_change(self, payload: Dict[str, Any]) -> None:
        item = str(payload["item"]).upper()
        index = self.model_index(str(payload["model"]), item) + int(payload["index"])
        value = float(payload["value"]) * float(payload.get("declared_scaling", 1.0))
        if item == "ICON":
            self._check(self.psspy.change_icon(index, int(value)), "change model ICON")
        elif item == "CON":
            self._check(self.psspy.change_con(index, float(value)), "change model CON")
        elif item == "VAR":
            self._check(self.psspy.change_var(index, float(value)), "change model VAR")
        else:
            raise PsseError("Runtime changes support ICON, CON and VAR; got {}".format(item))

    def source_impedance_ohm(self) -> Tuple[float, float]:
        branch = self.system["grid_branch"]
        rx = self._check(self.psspy.brndt2(int(branch["from_bus"]), int(branch["to_bus"]), str(branch.get("id", "1")), "RX"), "read grid impedance")
        base_kv = float(self._check(self.psspy.busdat(int(self.system["poc_bus"]), "BASE"), "read POC base kV"))
        zbase = base_kv * base_kv / 100.0
        return float(rx.real) * zbase, float(rx.imag) * zbase

    def apply_fault(self, payload: Dict[str, Any]) -> None:
        bus = self.resolve_bus(payload.get("bus", "fault"))
        source_r, source_x = self.source_impedance_ohm()
        r_fault, x_fault = fault_impedance_ohm(
            source_r, source_x, payload.get("zf_over_zs", 0.0), payload.get("fault_x_over_r", 0.0),
            payload.get("r_offset_ohm", 0.0), payload.get("x_offset_ohm", 0.0), payload.get("residual_voltage_pu"),
        )
        code = int(payload["type_code"])
        if code == 7:
            result = self.psspy.dist_3phase_bus_fault(ibus=bus, node=0, units=3, basekv=0.0, values1=r_fault, values2=x_fault)
        elif code == 1:
            result = self.psspy.dist_scmu_fault([0, 0, 1, bus], [r_fault, x_fault, 0.0, 0.0])
        elif code == 4:
            result = self.psspy.dist_scmu_fault([0, 0, 2, bus], [0.0, 0.0, r_fault, x_fault])
        elif code == 8:
            result = self.psspy.dist_scmu_fault([0, 0, 2, bus], [r_fault / 2.0, x_fault / 2.0, 9999.0, 9999.0])
        else:
            raise PsseError("Unsupported fault type code {}".format(code))
        self._check(result, "apply fault")

    def _change_fixed_shunt(self, bus: int, shunt_id: str, status: int, b_mvar: float) -> None:
        """Use the public PSS/E 34 fixed-shunt API, with an older-name fallback."""
        modern = getattr(self.psspy, "fixed_shunt_chng_3", None)
        if modern is not None:
            # PSS/E 34 signature: IBUS, ID, INTGAR(1), REALAR(2), NAME.
            result = modern(int(bus), str(shunt_id), [int(status)], [0.0, float(b_mvar)], self._s)
            self._check(result, "change fixed shunt")
            return
        legacy = getattr(self.psspy, "shunt_chng", None)
        if legacy is not None:
            self._check(
                legacy(int(bus), str(shunt_id), int(status), [0.0, float(b_mvar)]),
                "change fixed shunt",
            )
            return
        raise PsseError("This PSS/E installation exposes neither fixed_shunt_chng_3 nor shunt_chng")

    def apply_tov_shunt(self, payload: Dict[str, Any], enabled: bool) -> None:
        configured = self.system.get("fixed_shunts", {}).get("tov", {})
        bus = int(configured.get("bus", self.resolve_bus(payload.get("bus", "fault"))))
        shunt_id = str(configured.get("id", "1"))
        b_mvar = 0.0
        if enabled:
            capacitance_uf = float(payload.get("capacitance_uf", 0.0))
            base_kv = float(self._check(self.psspy.busdat(bus, "BASE"), "read TOV shunt base kV"))
            frequency_hz = float(self.config.section("dynamics").get("frequency_hz", 50.0))
            # Q(MVAr) = 2*pi*f*C(uF)*1e-6*V(kV)^2.
            b_mvar = 2.0 * math.pi * frequency_hz * capacitance_uf * 1.0e-6 * base_kv * base_kv
        self._change_fixed_shunt(bus, shunt_id, 1 if enabled else 0, b_mvar)

    def apply_event(self, event: Event, scenario: Scenario) -> None:
        payload = event.parameters
        if event.kind == "fault_apply":
            self.apply_fault(payload)
        elif event.kind == "fault_clear":
            self._check(self.psspy.dist_clear_fault(self.current_fault_number), "clear fault")
        elif event.kind == "grid_strength":
            r_pu, x_pu = impedance_from_fault_level(payload["fault_level_mva"], payload["x_over_r"])
            self.set_branch_impedance(self.branch(str(payload.get("branch", "grid"))), r_pu, x_pu)
        elif event.kind == "model_change":
            self.apply_model_change(payload)
        elif event.kind == "transformer_phase":
            transformer = self.config.section("transformers").get(str(payload["transformer"]))
            if not transformer:
                raise PsseError("Unknown transformer alias {!r}".format(payload["transformer"]))
            self._check(self.psspy.two_winding_chng_5(
                ibus=int(transformer["from_bus"]), jbus=int(transformer["to_bus"]), ckt=str(transformer.get("id", "1")),
                realari6=float(payload["phase_deg"]),
            ), "change transformer phase")
        elif event.kind == "load_change":
            load = self.system.get("loads", {}).get(str(payload["load"]))
            if not load:
                raise PsseError("Unknown load alias {!r}".format(payload["load"]))
            keyword = "realar1" if str(payload["quantity"]).upper() == "MW" else "realar2"
            arguments = {
                "ibus": int(load["bus"]),
                "id": str(load.get("id", "1")),
                keyword: float(payload["value"]),
            }
            self._check(self.psspy.load_chng_5(**arguments), "change load {}".format(payload["load"]))
        elif event.kind == "tov_shunt_apply":
            self.apply_tov_shunt(payload, True)
        elif event.kind == "tov_shunt_clear":
            self.apply_tov_shunt(payload, False)
        elif event.kind == "callback":
            handled = False
            if self.hooks and hasattr(self.hooks, "handle_event"):
                handled = bool(self.hooks.handle_event(self, event, scenario))
            if not handled:
                raise PsseError("Event {} requires implementation in project_hooks.py".format(event.kind))
        else:
            raise PsseError("Unknown event kind {!r}".format(event.kind))

    def run_to(self, time_s: float) -> None:
        dynamics = self.config.section("dynamics")
        self._check(
            self.psspy.run(
                option=0,
                tpause=float(time_s),
                nprt=int(dynamics.get("nprt", 5000)),
                nplt=int(self.steps_per_write),
            ),
            "run to {:.6g}s".format(time_s),
        )

    def halt(self) -> None:
        try:
            self.psspy.pssehalt_2()
        except Exception:
            pass
