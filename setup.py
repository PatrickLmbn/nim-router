from setuptools import setup, find_packages

setup(
    name="nim-router",
    version="1.0.0",
    description="Universal Multi-Provider Free Model Router",
    packages=find_packages(),
    py_modules=["nim-router"],
    entry_points={
        "console_scripts": [
            "nimrouter=nim_router.cli:main",
            "nim-router=nim_router.cli:main",
        ],
    },
    python_requires=">=3.8",
)
