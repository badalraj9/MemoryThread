
import json, re, os

root = r"D:\memorythread\MemoryThread"

def normalize_path(p):
    return p.replace(os.sep, "/")

all_files = []
for dirpath, dirnames, filenames in os.walk(root):
    if "node_modules" in dirpath or "__pycache__" in dirpath or ".venv" in dirpath or ".git" in dirpath:
        continue
    for fn in filenames:
        if fn.endswith(".py"):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            all_files.append(normalize_path(rel))

all_files.sort()

def get_internal_imports(rel_path):
    full = os.path.join(root, rel_path)
    imports = set()
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except:
        return imports
    for m in re.finditer(r"^\s*import\s+([a-zA-Z_][a-zA-Z0-9_.]*)", content, re.MULTILINE):
        mod = m.group(1).strip()
        if mod.startswith("memory_thread"):
            imports.add(mod)
    for m in re.finditer(r"^\s*from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import", content, re.MULTILINE):
        mod = m.group(1).strip()
        if mod.startswith("memory_thread"):
            imports.add(mod)
    return sorted(imports)

file_imports = {}
for f in all_files:
    imps = get_internal_imports(f)
    if imps:
        file_imports[f] = imps

reverse_map = {}
for f, imps in file_imports.items():
    for mod in imps:
        if mod not in reverse_map:
            reverse_map[mod] = []
        reverse_map[mod].append(f)

def file_to_module(f):
    mod = f.replace("/", ".").replace(".py", "")
    if mod.endswith(".__init__"):
        mod = mod[:-9]
    return mod

print("=" * 120)
print("COMPLETE INTERNAL IMPORT ANALYSIS FOR MemoryThread")
print("=" * 120)
print()
print("IMPORTS = which internal modules this file imports")
print("IMPORTED BY = which other files import this file's module path")
print("=" * 120)

root_files = [f for f in all_files if "/" not in f]
mt_files = [f for f in all_files if f.startswith("memory_thread/")]
tests_files = [f for f in all_files if f.startswith("tests/")]
scripts_files = [f for f in all_files if f.startswith("scripts/")]
bench_files = [f for f in all_files if f.startswith("benchmarks/")]
ex_files = [f for f in all_files if f.startswith("examples/")]

for section_label, section_files in [
    ("ROOT", root_files),
    ("memory_thread/", mt_files),
    ("tests/", tests_files),
    ("scripts/", scripts_files),
    ("benchmarks/", bench_files),
    ("examples/", ex_files),
]:
    print()
    print("#" * 120)
    print("#  SECTION: " + section_label)
    print("#" * 120)

    for f in section_files:
        imps = file_imports.get(f, [])
        file_mod = file_to_module(f)

        reverse_refs = []
        for mod, refs in reverse_map.items():
            if mod == file_mod or mod.startswith(file_mod + "."):
                for r in refs:
                    reverse_refs.append((mod, r))
        reverse_refs.sort()

        print()
        print("  --- " + f + " (module: " + file_mod + ") ---")
        print("  IMPORTS (internal):")
        if imps:
            for i in imps:
                print("    [import] " + i)
        else:
            print("    (no internal imports)")
        print("  IMPORTED BY (reverse refs):")
        if reverse_refs:
            for mod, ref in reverse_refs:
                print("    <- " + ref + "  (via " + mod + ")")
        else:
            print("    (not imported by any internal file)")

print()
print("=" * 120)
print("SUMMARY STATISTICS")
print("=" * 120)
mod_counts = [(mod, len(refs)) for mod, refs in reverse_map.items()]
mod_counts.sort(key=lambda x: -x[1])
print("  Total files with internal imports: " + str(len(file_imports)))
print("  Unique internal modules imported: " + str(len(reverse_map)))
print()
print("  Top 20 most imported modules:")
for mod, count in mod_counts[:20]:
    print("    " + mod + ": " + str(count) + " importers")
print()

# Also show the config files
print("=" * 120)
print("DEPENDENCY DECLARATION FILES")
print("=" * 120)
print()
print("--- requirements.txt ---")
with open(os.path.join(root, "requirements.txt")) as f:
    for line in f:
        line = line.strip()
        if line:
            print("  - " + line)
print()
print("--- pyproject.toml [project] dependencies ---")
with open(os.path.join(root, "pyproject.toml")) as f:
    content = f.read()
in_deps = False
for line in content.split("\n"):
    if 'dependencies = [' in line:
        in_deps = True
        continue
    if in_deps:
        if "]" in line:
            break
        dep = line.strip().strip(",").strip('"').strip("'")
        if dep:
            print("  - " + dep)
print()
print("--- pyproject.toml [project.optional-dependencies] ---")
opt_sections = re.findall(r"(\w+)\s*=\s*\[(.*?)\]", content, re.DOTALL)
for name, deps_str in opt_sections:
    if name in ("full",):
        continue
    deps = re.findall(r'"([^"]+)"', deps_str)
    if deps:
        print("  [" + name + "]")
        for d in deps:
            print("    - " + d)
