# Release 1.7.3 — PSS/E 34 dispatched-SAV save compatibility

## Fixed

- PSS/E no longer writes a hidden ``.dispatch_*.tmp.sav`` file directly into
  the persistent cache directory.  The engine now gives ``psspy.save`` only a
  conventional relative ``dispatch_*_tmp.sav`` filename inside the short
  shared runtime directory, then lets Python publish it into the cache after
  the PSS/E API call succeeds.
- A failed dispatch no longer causes later skipped scenarios to call
  ``PSSEHALT_2`` when PSS/E was not initialized, removing the misleading
  ``PSS(R)E not properly initialized (005331)`` messages.
- A failed PSS/E save now reports the exact output path, current directory,
  parent-directory state and path length for Windows diagnostics.
- Restores the established per-scenario result set: DYR, JSON, OUT, PNG, PDF
  and ``_initialised.sav``. The initialised SAV is staged under a short
  runtime filename after DYR/channel setup and before ``STRT``, then copied to
  the full scenario name; internal dispatch-cache SAVs remain separate.

## Validation

- Existing dispatch grouping, cache reuse and signal-profile tests remain in
  place.
- New regression checks require the PSS/E staging filename to be non-hidden,
  to use one conventional ``.sav`` suffix and to reside in the runtime folder.
- New backend coverage verifies that repeated or pre-initialization halt calls
  do not reach ``pssehalt_2``.
- Result-layout coverage verifies that every completed scenario publishes its
  renamed DYR and initialised SAV without leaving runtime staging files.

Real PSS/E 34 execution still requires validation on the licensed Windows
study machine.
