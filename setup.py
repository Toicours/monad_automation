from setuptools import setup, find_packages

setup(
    name="monad_automation",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "web3>=6.10.0",
        "python-dotenv>=1.0.0",
        "pydantic>=2.5.0",
        "eth-account>=0.9.0",
        "eth-utils>=2.3.0",
        "eth-typing>=3.4.0",
        "aiohttp>=3.8.6",
        "asyncio>=3.4.3",
        "loguru>=0.7.2",
        "click>=8.1.7",
        "tenacity>=8.2.3",
        "pyyaml>=6.0.1",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.3",
            "pytest-asyncio>=0.21.1",
            "pytest-mock>=3.12.0",
            "pytest-cov>=4.1.0",
            "black>=23.10.1",
            "isort>=5.12.0",
            "flake8>=6.1.0",
            "mypy>=1.6.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "monad_automation=main:cli",
        ],
    },
    python_requires=">=3.9",
    author="Your Name",
    author_email="your.email@example.com",
    description="Modular automation for Monad blockchain operations",
    keywords="blockchain, monad, automation, web3",
    url="https://github.com/yourusername/monad-automation",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)