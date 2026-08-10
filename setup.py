from setuptools import find_packages, setup


setup(
    name="heywood-bess-native-psse",
    version="1.8.0",
    description="Transparent SPEC-driven PSS/E automation and PSCAD post-processing",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    include_package_data=True,
    package_data={
        "hbess_open.appendices": ["*.cls", "report-assets/*"],
    },
    python_requires=">=3.9",
    install_requires=[
        "openpyxl==3.0.10; python_version<'3.8'",
        "openpyxl>=3.1.5; python_version>='3.8'",
        "numpy==1.21.6; python_version<'3.8'",
        "numpy>=1.23; python_version>='3.8'",
        "pandas==1.3.5; python_version<'3.8'",
        "pandas>=1.5,<3; python_version>='3.8'",
        "matplotlib>=3.3,<3.6; python_version<'3.8'",
        "matplotlib>=3.6; python_version>='3.8'",
    ],
    extras_require={"pscad": ["mhi.psout>=1.0"]},
    entry_points={"console_scripts": ["psse-open=psse_open.cli:main"]},
)
