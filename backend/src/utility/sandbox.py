import platform
import subprocess
import logging

logger = logging.getLogger("SandboxManager")

def is_windows_11_pro():
    """Checks if the OS is Windows 11 Pro."""
    try:
        # Check if Windows
        if platform.system() != "Windows":
            return False
            
        # Check version (Windows 11 is version 10.0.22000+)
        version_parts = platform.version().split('.')
        if len(version_parts) < 3:
            return False
        
        build_number = int(version_parts[2])
        is_win11 = build_number >= 22000
        
        if not is_win11:
            # We enforce Windows 11 as per request "check if the user has windows 11 pro"
            return False

        # Check Edition (Pro)
        # using PowerShell to get exact edition
        cmd = "Get-CimInstance Win32_OperatingSystem | Select-Object -ExpandProperty Caption"
        # CREATE_NO_WINDOW = 0x08000000
        result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=0x08000000)
        edition = result.stdout.strip()
        
        return "Pro" in edition
    except Exception as e:
        logger.error(f"Error checking Windows version: {e}")
        return False

def is_sandbox_enabled():
    """Checks if Windows Sandbox feature is enabled."""
    try:
        cmd = "Get-WindowsOptionalFeature -Online -FeatureName 'Containers-DisposableClientVM' | Select-Object -ExpandProperty State"
        result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=0x08000000)
        state = result.stdout.strip()
        return state == "Enabled"
    except Exception as e:
        logger.error(f"Error checking Sandbox status: {e}")
        return False

def enable_sandbox():
    """Enables Windows Sandbox feature via PowerShell."""
    try:
        cmd = "Enable-WindowsOptionalFeature -Online -FeatureName 'Containers-DisposableClientVM' -All -NoRestart"
        
        # This command generally requires Admin privileges.
        # If the app is not running as admin, this might fail or prompt UAC if handled by the OS (which subprocess doesn't do automatically for elevation).
        
        result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, creationflags=0x08000000)
        
        if result.returncode == 0:
            return True, "Sandbox feature enabled. Please restart your computer to apply changes."
        else:
            return False, f"Failed to enable. Ensure you are running as Administrator. Error: {result.stderr}"
    except Exception as e:
        return False, str(e)
