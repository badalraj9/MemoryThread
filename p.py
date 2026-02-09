import os

EXCLUDE_DIRS = {
    ".git", "__pycache__", "venv", ".venv",
    "node_modules", "build", "dist"
}

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

    level = root.count(os.sep)
    indent = "  " * level
    print(f"{indent}📁 {os.path.basename(root)}/")

    for f in files:
        if f.endswith(".py"):
            print(f"{indent}  📄 {f}")
