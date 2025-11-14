# Python Style Guide for ROCm Build Infrastructure

This guide documents Python coding standards and best practices for the ROCm build infrastructure projects.

## Core Principles

### 1. Fail-Fast Behavior

**Always fail immediately on errors. Never silently continue or produce incomplete results.**

❌ **Bad:**
```python
if not path.exists():
    print(f"Warning: Path does not exist: {path}")
    continue  # Silently produces incomplete output

try:
    process_file(path)
except Exception as e:
    print(f"Warning: {e}")
    # Continues with incomplete data
```

✅ **Good:**
```python
if not path.exists():
    raise FileNotFoundError(
        f"Path does not exist: {path}\n"
        f"This indicates a corrupted or incomplete artifact"
    )

# Let exceptions propagate - if we can't process, we must fail
process_file(path)
```

**Key points:**
- If data is missing, corrupted, or unreadable → raise an exception
- Don't catch exceptions unless you can meaningfully handle them
- "Warnings" that indicate data problems should be errors
- Incomplete artifacts are worse than failed builds

### 2. Use Dataclasses, Not Tuples

**For non-trivial data with multiple fields, use dataclasses instead of tuples.**

❌ **Bad:**
```python
def create_kpack_files(...) -> Dict[str, Tuple[Path, int, int]]:
    """Returns: Dict mapping arch to (kpack_path, size, kernel_count)"""
    return {"gfx1100": (path, 12345, 42)}  # What's what?
```

✅ **Good:**
```python
@dataclass
class KpackInfo:
    """Information about a created kpack file."""
    kpack_path: Path
    size: int
    kernel_count: int

def create_kpack_files(...) -> Dict[str, KpackInfo]:
    """Returns: Dict mapping arch to KpackInfo"""
    return {"gfx1100": KpackInfo(kpack_path=path, size=12345, kernel_count=42)}
```

**When tuples are OK:**
- Simple pairs where meaning is obvious: `(x, y)`, `(min, max)`
- Unpacking from standard library functions: `os.path.split()`
- Single-use internal return values that are immediately unpacked

### 3. Type Hints

**Always use specific type hints. Never use `Any` except in rare generic code.**

❌ **Bad:**
```python
from typing import Any

def process(handlers: List[Any]) -> Dict[str, Any]:
    pass
```

✅ **Good:**
```python
from rocm_kpack.database_handlers import DatabaseHandler

def process(handlers: List[DatabaseHandler]) -> Dict[str, KpackInfo]:
    pass
```

**Type hint best practices:**
- Import the actual types you need
- Use `Optional[T]` for nullable values
- Use specific return types (not `tuple`, use `Tuple[Path, int]`)
- For dict values with structure, define a dataclass

#### Extract Complex Type Signatures

**If a type signature is complex or repeated, extract it into a named type.**

❌ **Bad:**
```python
def parallel_prepare_kernels(
    archive: PackedKernelArchive,
    kernels: list[tuple[str, str, bytes, dict[str, object] | None]],
    executor: Executor | None = None,
) -> list[PreparedKernel]:
    """What is this tuple again? Have to read the docstring..."""
    for relative_path, gfx_arch, hsaco_data, metadata in kernels:
        ...
```

✅ **Good:**
```python
class KernelInput(NamedTuple):
    """Input data for preparing a kernel for packing.

    Attributes:
        relative_path: Path relative to archive root (e.g., "kernels/my_kernel")
        gfx_arch: GPU architecture (e.g., "gfx1100")
        hsaco_data: Raw HSACO binary data
        metadata: Optional metadata dict to store in TOC
    """
    relative_path: str
    gfx_arch: str
    hsaco_data: bytes
    metadata: dict[str, object] | None

def parallel_prepare_kernels(
    archive: PackedKernelArchive,
    kernels: list[KernelInput],  # Self-documenting!
    executor: Executor | None = None,
) -> list[PreparedKernel]:
    """Prepare multiple kernels in parallel..."""
    for k in kernels:
        # k.relative_path, k.gfx_arch, etc. - clear and IDE-friendly
        ...
```

**When to extract:**
- Type appears in multiple signatures → Use NamedTuple or TypeAlias
- Tuple has 3+ fields → Use NamedTuple or dataclass
- Type signature is hard to read at a glance → Extract it
- You find yourself documenting what tuple fields mean → Use NamedTuple

**What to use:**
- **NamedTuple**: Immutable, lightweight, for simple data containers
- **dataclass**: When you need methods, mutability, or inheritance
- **TypeAlias**: For complex generic types that are reused

### 4. Error Handling and Distinction

**Distinguish between different error conditions. Don't treat all errors the same.**

❌ **Bad:**
```python
try:
    with open(file_path, 'rb') as f:
        magic = f.read(4)
        if magic != b'\x7fELF':
            return False
    output = subprocess.check_output([readelf, "-S", str(file_path)])
    return ".hip_fatbin" in output
except Exception:
    return False  # File not found? Not ELF? readelf crashed? Who knows!
```

✅ **Good:**
```python
# Fast check: Is this even an ELF file?
try:
    with open(file_path, 'rb') as f:
        magic = f.read(4)
        if magic != b'\x7fELF':
            return False  # Not ELF, definitely not fat
except FileNotFoundError:
    raise  # Propagate - caller should know file is missing
except OSError as e:
    raise RuntimeError(f"Cannot read file {file_path}: {e}") from e

# Now check for .hip_fatbin section
try:
    output = subprocess.check_output([readelf, "-S", str(file_path)])
    return ".hip_fatbin" in output
except subprocess.CalledProcessError as e:
    if e.returncode == 1:
        return False  # readelf returns 1 for valid ELF without target section
    raise RuntimeError(f"readelf failed on {file_path}: {e.output}") from e
except FileNotFoundError as e:
    raise RuntimeError(f"readelf not found: {readelf}") from e
```

**Key points:**
- Catch specific exceptions, not broad `Exception`
- Re-raise exceptions that indicate bugs or missing tools
- Return False only for legitimate "not found" cases
- Use `from e` to preserve exception chain

### 5. No Timeouts on Basic Binutils

**NEVER add timeouts to basic binutils operations (readelf, objcopy, etc.).**

❌ **Bad:**
```python
subprocess.check_output([readelf, "-S", file], timeout=10)
```

✅ **Good:**
```python
subprocess.check_output([readelf, "-S", file])
```

**Why:** Timeouts cause spurious failures on systems under load. If a tool hangs, that's a bug in the tool or corrupted input, not something a timeout will fix.

### 6. Output Validation

**Validate that operations actually succeeded. Don't assume.**

❌ **Bad:**
```python
archive.write(kpack_file)
# Assume it worked
kpack_size = kpack_file.stat().st_size
```

✅ **Good:**
```python
archive.write(kpack_file)

# Validate kpack file was created successfully
if not kpack_file.exists():
    raise RuntimeError(f"Failed to create kpack file: {kpack_file}")

kpack_size = kpack_file.stat().st_size
if kpack_size == 0:
    raise RuntimeError(f"Kpack file is empty: {kpack_file}")
```

**What to validate:**
- Files exist after creation
- Files are non-empty when they should have content
- Processed files are smaller after stripping
- Critical operations completed successfully

### 7. No Magic Numbers

**Don't use unexplained magic numbers, especially for estimates.**

❌ **Bad:**
```python
original_size = binary_path.stat().st_size + 8000000  # Estimate original size
print(f"Stripped {original_size - new_size} bytes")
```

✅ **Good:**
```python
# Either track the real size or don't log it
new_size = binary_path.stat().st_size
print(f"Device code stripped, new size: {new_size} bytes")
```

### 8. Performance Best Practices

**Optimize hot paths, but keep code readable.**

❌ **Bad:**
```python
# Compiles regex on every call
def detect(self, path: Path) -> Optional[str]:
    match = re.search(r'gfx(\d+[a-z]*)', path.name)
```

✅ **Good:**
```python
# Compile once at module level
_GFX_ARCH_PATTERN = re.compile(r'gfx(\d+[a-z]*)')

def detect(self, path: Path) -> Optional[str]:
    match = _GFX_ARCH_PATTERN.search(path.name)
```

**Other optimizations:**
- Check cheap conditions before expensive ones (e.g., magic bytes before subprocess)
- Cache expensive computations when called repeatedly
- Use generators for large datasets

### 9. Import Organization

**Put all imports at the top of the file. Avoid inline imports except for rare special cases.**

❌ **Bad:**
```python
def process_binary(input_path: Path, output_path: Path) -> None:
    """Process a binary file."""
    # ... some code ...

    if needs_special_processing:
        import shutil  # Inline import
        shutil.copy2(input_path, temp_file)
```

✅ **Good:**
```python
import shutil
from pathlib import Path

def process_binary(input_path: Path, output_path: Path) -> None:
    """Process a binary file."""
    # ... some code ...

    if needs_special_processing:
        shutil.copy2(input_path, temp_file)
```

**When inline imports ARE acceptable:**
- **Circular dependency workaround**: If module A imports module B and B imports A, one can use an inline import
- **Optional heavy dependency**: Importing a very heavy module that's rarely used (but document why)

**Example of acceptable inline import for circular dependency:**
```python
def create_host_only(self, output_path: Path) -> None:
    """Create host-only binary."""
    # Import here to avoid circular dependency:
    # binutils.py → elf_offload_kpacker.py → binutils.py
    from rocm_kpack.elf_offload_kpacker import kpack_offload_binary
    kpack_offload_binary(self.file_path, output_path, toolchain=self.toolchain)
```

**Key points:**
- Inline imports should be the exception, not the rule
- Always add a comment explaining WHY the import is inline
- Consider refactoring to eliminate circular dependencies instead

### 10. Code Organization

**Keep functions focused and modules cohesive.**

**Class size guidelines:**
- Classes should be < 200 lines (ideally)
- Methods should be < 30 lines (ideally)
- If a class has 7+ responsibilities, split it

**When to split:**
- God objects doing everything → multiple focused classes
- 100+ line methods → extract helper methods
- Duplicate code → extract to shared function

### 11. No Duplicate Code

**Extract common code to shared functions.**

❌ **Bad:**
```python
# In method 1:
depth = len(binary_relpath.parts) - 1
if depth == 0:
    manifest_relpath = f".kpack/{self.component_name}.kpm"
else:
    up_path = "../" * depth
    manifest_relpath = f"{up_path}.kpack/{self.component_name}.kpm"

# In method 2:
# Same code repeated
```

✅ **Good:**
```python
def compute_manifest_relative_path(self, binary_path: Path, prefix_root: Path) -> str:
    """Compute the relative path from a binary to its kpack manifest."""
    rel_path = binary_path.relative_to(prefix_root)
    depth = len(rel_path.parts) - 1
    if depth == 0:
        return f".kpack/{self.component_name}.kpm"
    else:
        up_path = "/".join([".."] * depth)
        return f"{up_path}/.kpack/{self.component_name}.kpm"

# Use in both places
manifest_relpath = self.compute_manifest_relative_path(binary_path, prefix_dir)
```

## Code Review Checklist

Before submitting code, verify:

- [ ] No silent error handling (fail-fast on all errors)
- [ ] No `Any` type hints (use specific types)
- [ ] Complex type signatures extracted to NamedTuple/dataclass
- [ ] No magic numbers or fake estimates
- [ ] Tuples only for simple pairs, dataclasses for structured data
- [ ] All imports at top of file (except documented circular dependencies)
- [ ] No timeouts on binutils operations
- [ ] Output validation after critical operations
- [ ] No duplicate code
- [ ] Specific exception handling (not broad `except Exception`)
- [ ] Methods < 30 lines (or have a good reason)
- [ ] Classes < 200 lines (or split into focused components)

## Testing Standards

**Tests should verify fail-fast behavior:**

```python
def test_fails_on_missing_file(self, tmp_path):
    """Test that processing fails fast on missing files."""
    splitter = ArtifactSplitter(...)

    non_existent = tmp_path / "non_existent"

    # Should raise, not continue with incomplete data
    with pytest.raises(FileNotFoundError, match="does not exist"):
        splitter.split(non_existent, output_dir)
```

**Use real files in tests when possible:**
- Prefer real temporary files over mocks for filesystem operations
- Mock only external dependencies (network, expensive tools)
- Integration tests should exercise the full path

## Common Patterns

### Pattern: Reading and Validating a File

```python
def read_config(path: Path) -> ConfigData:
    """Read and validate configuration file."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e
    except OSError as e:
        raise RuntimeError(f"Cannot read {path}: {e}") from e

    # Validate required fields
    if 'version' not in data:
        raise ValueError(f"Missing 'version' field in {path}")

    return ConfigData(**data)
```

### Pattern: Running Subprocess with Proper Error Handling

```python
def run_binutil(tool: Path, args: List[str], input_file: Path) -> str:
    """Run a binutil tool with proper error handling."""
    try:
        result = subprocess.check_output(
            [str(tool)] + args + [str(input_file)],
            stderr=subprocess.STDOUT,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        # Distinguish between different exit codes
        if e.returncode == 1:
            # Tool-specific handling for returncode 1
            return ""
        raise RuntimeError(
            f"{tool.name} failed on {input_file} with code {e.returncode}: {e.output}"
        ) from e
    except FileNotFoundError as e:
        raise RuntimeError(f"Tool not found: {tool}") from e
```

## Notes

- This guide reflects lessons learned from production incidents where silent failures caused data corruption
- When in doubt, fail fast and loud
- False positives (spurious errors) are better than false negatives (silent corruption)
