import setuptools
import os

# Read the contents of README file
from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

# Read the version from __init__.py
version = {}
with open(os.path.join(this_directory, "ripzilla", "__init__.py")) as fp:
    exec(fp.read(), version)

setuptools.setup(
    name="ripzilla",
    version=version["__version__"],
    author="Your Name", # TODO: Replace with actual author name
    author_email="your.email@example.com", # TODO: Replace with actual author email
    description="A robust library to extract audio from local or remote videos.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/ripzilla", # TODO: Replace with actual URL
    packages=setuptools.find_packages(),
    install_requires=[
        "tenacity>=8.2.0",
        "requests>=2.25.0",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License", # TODO: Choose appropriate license
        "Operating System :: OS Independent",
        "Topic :: Multimedia :: Sound/Audio :: Conversion",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.8",
    # Add entry point for a potential CLI tool
    entry_points={
        "console_scripts": [
            "ripzilla = ripzilla.cli:main", # Assumes cli.py with a main() function
        ],
    },
) 