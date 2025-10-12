"""
Setup configuration for semantic-copycat-oslili package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="semantic-copycat-oslili",
    version="1.4.1",
    author="Oscar Valenzuela B.",
    author_email="oscar.valenzuela.b@gmail.com",
    description="License and copyright detector for software packages",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/oscarvalenzuelab/semantic-copycat-oslili",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "ml": [
            "transformers>=4.30.0",
            "torch>=2.0.0",
            "scikit-learn>=1.3.0",
        ],
        "cyclonedx": [
            "cyclonedx-python-lib>=4.0.0",
        ],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
            "isort>=5.12.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "oslili=semantic_copycat_oslili.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "semantic_copycat_oslili": ["data/*.json", "data/*.yaml"],
    },
)