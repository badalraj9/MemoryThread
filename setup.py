"""
Memory Thread - Setup Script (Legacy)

For modern installation, use pyproject.toml:
    pip install .
    pip install .[full]  # All extras
    pip install .[dev]   # Development

This file is for backward compatibility with older pip versions.
"""
from setuptools import setup, find_packages

setup(
    name="memory-thread",
    version="1.0.0",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "pydantic>=2.0",
        "networkx>=3.0",
        "sentence-transformers>=2.0",
        "python-dotenv>=1.0",
    ],
    extras_require={
        "api": ["fastapi>=0.100", "uvicorn>=0.20"],
        "db": ["psycopg2-binary>=2.9", "qdrant-client>=1.5"],
        "streaming": ["pyzmq>=25.0", "aiokafka>=0.8"],
        "tui": ["textual>=0.40"],
        "nlp": ["spacy>=3.5"],
        "dev": ["pytest>=7.0", "pytest-asyncio>=0.21", "black>=23.0", "ruff>=0.1"],
    },
    entry_points={
        "console_scripts": [
            "mt=memory_thread.cli:main",
        ],
    },
    author="Badal Raj",
    description="A truth-preserving cognitive memory system for AI",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/badalraj/MemoryThread",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
    ],
)
