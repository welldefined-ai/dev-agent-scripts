from setuptools import setup

setup(
    name="cli-log",
    version="0.1.0",
    py_modules=["cli_log"],
    entry_points={
        "console_scripts": [
            "cli-log=cli_log:main",
        ],
    },
    python_requires=">=3.6",
)