from setuptools import setup

setup(
    name="charles_analizer",
    version="0.1.0",
    packages=["charles_analizer"],
    package_dir={"charles_analizer": "."},
    package_data={"charles_analizer": ["*.chlz"]},
    include_package_data=True,
    py_modules=["analyze"],
    entry_points={
        "console_scripts": [
            "charles-analizer = charles_analizer.cli:main",
            "charles-web = charles_analizer.server:main",
        ],
    },
)
