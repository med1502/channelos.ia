from setuptools import setup, find_packages

setup(
    name="channelos",
    version="1.0.0",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "channelos=channelos.main:main",
        ],
    },
    python_requires=">=3.10",
)
