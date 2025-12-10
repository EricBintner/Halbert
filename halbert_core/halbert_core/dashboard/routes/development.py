"""
Development Environment API Routes

Provides endpoints for development environment detection.
Phase 16: Development Environment
"""

import logging
import subprocess
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from fastapi import APIRouter, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = object

logger = logging.getLogger("halbert.development")
router = APIRouter(prefix="/development", tags=["development"])


def run_command(cmd: List[str], timeout: int = 10) -> Optional[str]:
    """Run a command and return stdout, or None on error."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def which(cmd: str) -> Optional[str]:
    """Find path to command."""
    return run_command(["which", cmd])


# Language detection configurations
LANGUAGE_CONFIGS = [
    {"name": "python3", "cmd": ["python3", "--version"], "pattern": r"Python (\S+)"},
    {"name": "python", "cmd": ["python", "--version"], "pattern": r"Python (\S+)"},
    {"name": "node", "cmd": ["node", "--version"], "pattern": r"v?(\S+)"},
    {"name": "rust", "cmd": ["rustc", "--version"], "pattern": r"rustc (\S+)"},
    {"name": "go", "cmd": ["go", "version"], "pattern": r"go(\S+)"},
    {"name": "java", "cmd": ["java", "--version"], "pattern": r"openjdk (\S+)|java (\S+)"},
    {"name": "ruby", "cmd": ["ruby", "--version"], "pattern": r"ruby (\S+)"},
    {"name": "php", "cmd": ["php", "--version"], "pattern": r"PHP (\S+)"},
    {"name": "perl", "cmd": ["perl", "--version"], "pattern": r"v(\S+)"},
    {"name": "lua", "cmd": ["lua", "-v"], "pattern": r"Lua (\S+)"},
    {"name": "r", "cmd": ["R", "--version"], "pattern": r"R version (\S+)"},
    {"name": "julia", "cmd": ["julia", "--version"], "pattern": r"julia version (\S+)"},
    {"name": "elixir", "cmd": ["elixir", "--version"], "pattern": r"Elixir (\S+)"},
    {"name": "scala", "cmd": ["scala", "-version"], "pattern": r"Scala.* version (\S+)"},
    {"name": "kotlin", "cmd": ["kotlin", "-version"], "pattern": r"Kotlin version (\S+)"},
    {"name": "swift", "cmd": ["swift", "--version"], "pattern": r"Swift version (\S+)"},
    {"name": "dotnet", "cmd": ["dotnet", "--version"], "pattern": r"(\S+)"},
    {"name": "deno", "cmd": ["deno", "--version"], "pattern": r"deno (\S+)"},
    {"name": "bun", "cmd": ["bun", "--version"], "pattern": r"(\S+)"},
]

# Tool detection configurations
TOOL_CONFIGS = [
    {"name": "git", "cmd": ["git", "--version"], "pattern": r"git version (\S+)"},
    {"name": "docker", "cmd": ["docker", "--version"], "pattern": r"Docker version (\S+)"},
    {"name": "podman", "cmd": ["podman", "--version"], "pattern": r"podman version (\S+)"},
    {"name": "make", "cmd": ["make", "--version"], "pattern": r"GNU Make (\S+)"},
    {"name": "cmake", "cmd": ["cmake", "--version"], "pattern": r"cmake version (\S+)"},
    {"name": "npm", "cmd": ["npm", "--version"], "pattern": r"(\S+)"},
    {"name": "yarn", "cmd": ["yarn", "--version"], "pattern": r"(\S+)"},
    {"name": "pnpm", "cmd": ["pnpm", "--version"], "pattern": r"(\S+)"},
    {"name": "pip", "cmd": ["pip", "--version"], "pattern": r"pip (\S+)"},
    {"name": "cargo", "cmd": ["cargo", "--version"], "pattern": r"cargo (\S+)"},
    {"name": "composer", "cmd": ["composer", "--version"], "pattern": r"Composer version (\S+)"},
    {"name": "bundler", "cmd": ["bundle", "--version"], "pattern": r"Bundler version (\S+)"},
    {"name": "gradle", "cmd": ["gradle", "--version"], "pattern": r"Gradle (\S+)"},
    {"name": "maven", "cmd": ["mvn", "--version"], "pattern": r"Apache Maven (\S+)"},
    {"name": "gcc", "cmd": ["gcc", "--version"], "pattern": r"gcc.* (\d+\.\d+\.\d+)"},
    {"name": "clang", "cmd": ["clang", "--version"], "pattern": r"clang version (\S+)"},
    {"name": "curl", "cmd": ["curl", "--version"], "pattern": r"curl (\S+)"},
    {"name": "wget", "cmd": ["wget", "--version"], "pattern": r"GNU Wget (\S+)"},
    {"name": "jq", "cmd": ["jq", "--version"], "pattern": r"jq-(\S+)"},
    {"name": "ripgrep", "cmd": ["rg", "--version"], "pattern": r"ripgrep (\S+)"},
    {"name": "fd", "cmd": ["fd", "--version"], "pattern": r"fd (\S+)"},
    {"name": "fzf", "cmd": ["fzf", "--version"], "pattern": r"(\S+)"},
    {"name": "tmux", "cmd": ["tmux", "-V"], "pattern": r"tmux (\S+)"},
]


def detect_languages() -> List[Dict[str, str]]:
    """Detect installed programming languages."""
    import re
    languages = []
    seen = set()
    
    for config in LANGUAGE_CONFIGS:
        output = run_command(config["cmd"])
        if output:
            match = re.search(config["pattern"], output, re.I)
            version = match.group(1) if match else output.split()[0]
            path = which(config["cmd"][0])
            
            # Skip if we already have this language (e.g., python vs python3)
            if config["name"] in seen:
                continue
            if config["name"] == "python" and "python3" in seen:
                continue
                
            seen.add(config["name"])
            languages.append({
                "name": config["name"],
                "version": version,
                "path": path or "",
            })
    
    return languages


def detect_tools() -> List[Dict[str, str]]:
    """Detect installed development tools."""
    import re
    tools = []
    
    for config in TOOL_CONFIGS:
        output = run_command(config["cmd"])
        if output:
            match = re.search(config["pattern"], output, re.I)
            version = match.group(1) if match else output.split()[0] if output else "installed"
            path = which(config["cmd"][0])
            
            tools.append({
                "name": config["name"],
                "version": version,
                "path": path or "",
            })
    
    return tools



def detect_package_managers() -> List[str]:
    """Detect installed package managers."""
    managers = []
    checks = [
        ("apt", "apt"),
        ("dnf", "dnf"),
        ("yum", "yum"),
        ("pacman", "pacman"),
        ("zypper", "zypper"),
        ("brew", "brew"),
        ("nix", "nix"),
        ("flatpak", "flatpak"),
        ("snap", "snap"),
    ]
    
    for name, cmd in checks:
        if which(cmd):
            managers.append(name)
    
    return managers


def detect_version_managers() -> List[Dict[str, Any]]:
    """Detect installed version managers and their managed versions."""
    import re
    managers = []
    home = Path.home()
    
    # NVM (Node Version Manager)
    nvm_dir = home / ".nvm"
    if nvm_dir.exists():
        versions = []
        versions_dir = nvm_dir / "versions" / "node"
        if versions_dir.exists():
            for v in sorted(versions_dir.iterdir(), reverse=True):
                if v.is_dir() and v.name.startswith("v"):
                    versions.append(v.name)
        
        # Get current nvm version
        current = None
        nvm_current = run_command(["bash", "-c", "source ~/.nvm/nvm.sh && nvm current"])
        if nvm_current and nvm_current != "system":
            current = nvm_current
        
        # Check for LTS info
        lts_info = None
        # Could add web lookup for latest LTS here in future
        
        managers.append({
            "name": "nvm",
            "type": "node",
            "path": str(nvm_dir),
            "versions": versions[:10],  # Limit to 10
            "total_versions": len(versions),
            "current": current,
            "lts_available": lts_info,
        })
    
    # Pyenv
    pyenv_root = Path(os.environ.get("PYENV_ROOT", home / ".pyenv"))
    if pyenv_root.exists():
        versions = []
        versions_dir = pyenv_root / "versions"
        if versions_dir.exists():
            for v in sorted(versions_dir.iterdir(), reverse=True):
                if v.is_dir() and not v.is_symlink():
                    # Check if it's a version or a venv
                    if re.match(r"^\d+\.\d+", v.name):
                        versions.append(v.name)
        
        current = run_command(["pyenv", "version-name"])
        
        managers.append({
            "name": "pyenv",
            "type": "python",
            "path": str(pyenv_root),
            "versions": versions[:10],
            "total_versions": len(versions),
            "current": current,
            "lts_available": None,
        })
    
    # Rbenv
    rbenv_root = home / ".rbenv"
    if rbenv_root.exists():
        versions = []
        versions_dir = rbenv_root / "versions"
        if versions_dir.exists():
            for v in sorted(versions_dir.iterdir(), reverse=True):
                if v.is_dir():
                    versions.append(v.name)
        
        current = run_command(["rbenv", "version-name"])
        
        managers.append({
            "name": "rbenv",
            "type": "ruby",
            "path": str(rbenv_root),
            "versions": versions[:10],
            "total_versions": len(versions),
            "current": current,
            "lts_available": None,
        })
    
    # Goenv
    goenv_root = home / ".goenv"
    if goenv_root.exists():
        versions = []
        versions_dir = goenv_root / "versions"
        if versions_dir.exists():
            for v in sorted(versions_dir.iterdir(), reverse=True):
                if v.is_dir():
                    versions.append(v.name)
        
        current = run_command(["goenv", "version-name"])
        
        managers.append({
            "name": "goenv",
            "type": "go",
            "path": str(goenv_root),
            "versions": versions[:10],
            "total_versions": len(versions),
            "current": current,
            "lts_available": None,
        })
    
    # SDKMAN (Java, Kotlin, Scala, etc.)
    sdkman_dir = home / ".sdkman"
    if sdkman_dir.exists():
        candidates_dir = sdkman_dir / "candidates"
        if candidates_dir.exists():
            for candidate in candidates_dir.iterdir():
                if candidate.is_dir():
                    versions = []
                    for v in sorted(candidate.iterdir(), reverse=True):
                        if v.is_dir() and v.name != "current":
                            versions.append(v.name)
                    
                    current = None
                    current_link = candidate / "current"
                    if current_link.is_symlink():
                        current = current_link.resolve().name
                    
                    if versions:
                        managers.append({
                            "name": f"sdkman-{candidate.name}",
                            "type": candidate.name,
                            "path": str(candidate),
                            "versions": versions[:10],
                            "total_versions": len(versions),
                            "current": current,
                            "lts_available": None,
                        })
    
    # asdf (universal version manager)
    asdf_dir = home / ".asdf"
    if asdf_dir.exists():
        installs_dir = asdf_dir / "installs"
        if installs_dir.exists():
            for plugin in installs_dir.iterdir():
                if plugin.is_dir():
                    versions = []
                    for v in sorted(plugin.iterdir(), reverse=True):
                        if v.is_dir():
                            versions.append(v.name)
                    
                    if versions:
                        managers.append({
                            "name": f"asdf-{plugin.name}",
                            "type": plugin.name,
                            "path": str(plugin),
                            "versions": versions[:10],
                            "total_versions": len(versions),
                            "current": None,
                            "lts_available": None,
                        })
    
    # rustup (Rust toolchain manager)
    rustup_dir = home / ".rustup"
    if rustup_dir.exists():
        toolchains_dir = rustup_dir / "toolchains"
        if toolchains_dir.exists():
            versions = []
            for v in sorted(toolchains_dir.iterdir(), reverse=True):
                if v.is_dir():
                    versions.append(v.name)
            
            current = run_command(["rustup", "default"])
            if current:
                current = current.split()[0] if current else None
            
            if versions:
                managers.append({
                    "name": "rustup",
                    "type": "rust",
                    "path": str(rustup_dir),
                    "versions": versions[:10],
                    "total_versions": len(versions),
                    "current": current,
                    "lts_available": None,
                })
    
    return managers


def detect_virtual_environments() -> List[Dict[str, Any]]:
    """Detect Python virtual environments, conda envs, etc."""
    environments = []
    home = Path.home()
    
    # Common venv locations to search
    search_paths = [
        home,
        home / "projects",
        home / "Projects", 
        home / "code",
        home / "Code",
        home / "dev",
        home / "Development",
        home / "work",
        home / "Work",
    ]
    
    seen_envs = set()
    
    # Find Python venvs by looking for pyvenv.cfg or bin/activate
    for search_path in search_paths:
        if not search_path.exists():
            continue
        
        try:
            # Look for pyvenv.cfg (standard venv marker)
            for pyvenv_cfg in search_path.rglob("pyvenv.cfg"):
                env_path = pyvenv_cfg.parent
                if str(env_path) in seen_envs:
                    continue
                seen_envs.add(str(env_path))
                
                # Determine parent project
                project_path = env_path.parent
                if env_path.name in [".venv", "venv", "env", ".env"]:
                    project_name = project_path.name
                else:
                    project_name = None
                
                # Get Python version from the venv
                python_path = env_path / "bin" / "python"
                python_version = None
                if python_path.exists():
                    version_output = run_command([str(python_path), "--version"])
                    if version_output:
                        python_version = version_output.replace("Python ", "")
                
                # Count installed packages
                site_packages = list((env_path / "lib").glob("python*/site-packages"))
                package_count = 0
                if site_packages:
                    package_count = len([p for p in site_packages[0].iterdir() 
                                        if p.is_dir() and not p.name.endswith(".dist-info")])
                
                environments.append({
                    "name": env_path.name,
                    "type": "venv",
                    "path": str(env_path),
                    "project": project_name,
                    "project_path": str(project_path) if project_name else None,
                    "python_version": python_version,
                    "package_count": package_count,
                })
                
                if len(environments) >= 50:  # Limit search
                    break
        except PermissionError:
            continue
        except Exception as e:
            logger.debug(f"Error scanning {search_path}: {e}")
    
    # Conda environments
    conda_path = which("conda")
    if conda_path:
        try:
            import json
            envs_output = run_command(["conda", "env", "list", "--json"])
            if envs_output:
                envs_data = json.loads(envs_output)
                for env_path_str in envs_data.get("envs", []):
                    env_path = Path(env_path_str)
                    if str(env_path) in seen_envs:
                        continue
                    seen_envs.add(str(env_path))
                    
                    # Get Python version
                    python_path = env_path / "bin" / "python"
                    python_version = None
                    if python_path.exists():
                        version_output = run_command([str(python_path), "--version"])
                        if version_output:
                            python_version = version_output.replace("Python ", "")
                    
                    # Determine if base or named env
                    is_base = "miniconda" in str(env_path).lower() or "anaconda" in str(env_path).lower()
                    
                    environments.append({
                        "name": "base" if is_base and env_path.name in ["miniconda3", "anaconda3"] else env_path.name,
                        "type": "conda",
                        "path": str(env_path),
                        "project": None,
                        "project_path": None,
                        "python_version": python_version,
                        "package_count": None,
                    })
        except Exception as e:
            logger.debug(f"Error listing conda envs: {e}")
    
    # Poetry environments (in ~/.cache/pypoetry/virtualenvs)
    poetry_cache = home / ".cache" / "pypoetry" / "virtualenvs"
    if poetry_cache.exists():
        try:
            for env_dir in poetry_cache.iterdir():
                if env_dir.is_dir() and str(env_dir) not in seen_envs:
                    seen_envs.add(str(env_dir))
                    
                    # Poetry envs are named like "project-name-py3.11"
                    parts = env_dir.name.rsplit("-py", 1)
                    project_name = parts[0] if len(parts) == 2 else env_dir.name
                    
                    python_path = env_dir / "bin" / "python"
                    python_version = None
                    if python_path.exists():
                        version_output = run_command([str(python_path), "--version"])
                        if version_output:
                            python_version = version_output.replace("Python ", "")
                    
                    environments.append({
                        "name": env_dir.name,
                        "type": "poetry",
                        "path": str(env_dir),
                        "project": project_name,
                        "project_path": None,
                        "python_version": python_version,
                        "package_count": None,
                    })
        except Exception as e:
            logger.debug(f"Error scanning poetry envs: {e}")
    
    return environments


def discover_projects(search_dirs: Optional[List[str]] = None, max_depth: int = 3, max_projects: int = 20) -> List[Dict[str, Any]]:
    """Discover development projects (git repos, etc.)."""
    if search_dirs is None:
        home = Path.home()
        search_dirs = [
            str(home),
            str(home / "projects"),
            str(home / "Projects"),
            str(home / "code"),
            str(home / "Code"),
            str(home / "dev"),
            str(home / "Development"),
            str(home / "src"),
            str(home / "repos"),
            str(home / "work"),
            str(home / "Work"),
        ]
    
    projects = []
    seen_paths = set()
    
    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if not search_path.exists():
            continue
        
        # Find .git directories
        try:
            for depth in range(1, max_depth + 1):
                pattern = "/".join(["*"] * depth) + "/.git"
                for git_dir in search_path.glob(pattern):
                    if len(projects) >= max_projects:
                        break
                    
                    project_path = git_dir.parent
                    if str(project_path) in seen_paths:
                        continue
                    seen_paths.add(str(project_path))
                    
                    # Determine project type
                    project_type = "git"
                    languages = []
                    
                    if (project_path / "package.json").exists():
                        project_type = "node"
                        languages.append("javascript")
                    elif (project_path / "Cargo.toml").exists():
                        project_type = "rust"
                        languages.append("rust")
                    elif (project_path / "go.mod").exists():
                        project_type = "go"
                        languages.append("go")
                    elif (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists():
                        project_type = "python"
                        languages.append("python")
                    
                    # Get git branch
                    branch = run_command(["git", "-C", str(project_path), "branch", "--show-current"])
                    
                    # Get git status
                    status_output = run_command(["git", "-C", str(project_path), "status", "--porcelain"])
                    git_status = "clean"
                    if status_output:
                        git_status = "dirty"
                    
                    # Get last modified time
                    try:
                        mtime = project_path.stat().st_mtime
                        import datetime
                        last_modified = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                    except Exception:
                        last_modified = "unknown"
                    
                    projects.append({
                        "name": project_path.name,
                        "path": str(project_path),
                        "type": project_type,
                        "languages": languages,
                        "last_modified": last_modified,
                        "git_branch": branch,
                        "git_status": git_status,
                    })
        except PermissionError:
            continue
        except Exception as e:
            logger.warning(f"Error scanning {search_dir}: {e}")
    
    # Sort by last modified (most recent first)
    projects.sort(key=lambda p: p["last_modified"], reverse=True)
    
    return projects[:max_projects]


def get_dev_info() -> Dict[str, Any]:
    """Get full development environment information."""
    languages = detect_languages()
    tools = detect_tools()
    package_managers = detect_package_managers()
    version_managers = detect_version_managers()
    virtual_environments = detect_virtual_environments()
    projects = discover_projects()
    
    return {
        "languages": languages,
        "tools": tools,
        "projects": projects,
        "package_managers": package_managers,
        "version_managers": version_managers,
        "virtual_environments": virtual_environments,
        "stats": {
            "total_languages": len(languages),
            "total_tools": len(tools),
            "total_projects": len(projects),
            "total_version_managers": len(version_managers),
            "total_virtual_environments": len(virtual_environments),
        },
    }


if FASTAPI_AVAILABLE:
    
    @router.get("/info")
    async def get_development_data() -> Dict[str, Any]:
        """Get development environment information."""
        try:
            return get_dev_info()
        except Exception as e:
            logger.error(f"Failed to get development info: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    
    @router.get("/languages")
    async def get_languages() -> Dict[str, Any]:
        """Get installed programming languages."""
        return {"languages": detect_languages()}
    
    
    @router.get("/tools")
    async def get_tools() -> Dict[str, Any]:
        """Get installed development tools."""
        return {"tools": detect_tools()}
    
    
    @router.get("/projects")
    async def get_projects(max_depth: int = 3, max_projects: int = 20) -> Dict[str, Any]:
        """Discover development projects."""
        return {"projects": discover_projects(max_depth=max_depth, max_projects=max_projects)}
