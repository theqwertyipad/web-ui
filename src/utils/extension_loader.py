import logging
import os
import shutil
import tempfile
from typing import List, Optional

logger = logging.getLogger(__name__)


def get_extension_path() -> str:
    """
    Get the path to the workflow recorder extension

    Returns:
        str: Path to the extension directory
    """
    # Path to the extension in the project
    base_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    extension_path = os.path.join(
        base_dir, "src", "workflow", "recorder_extension", "dist"
    )

    if not os.path.exists(extension_path):
        logger.warning(f"Extension directory not found at {extension_path}")
        return ""

    return extension_path


def prepare_browser_args(
    headless: bool = False, extension_path: Optional[str] = None
) -> List[str]:
    """
    Prepare browser arguments for launching Chrome with extensions

    Args:
        headless: Whether to run browser in headless mode
        extension_path: Path to the extension directory

    Returns:
        List[str]: List of browser arguments
    """
    args = []

    # Basic browser configuration
    args.append("--no-sandbox")
    args.append("--disable-setuid-sandbox")
    args.append("--disable-dev-shm-usage")
    args.append("--disable-gpu")
    args.append(
        "--disable-extensions-except={}".format(extension_path or get_extension_path())
    )
    args.append("--load-extension={}".format(extension_path or get_extension_path()))

    # Non-headless mode is required for extension to work properly
    if not headless:
        args.append("--window-size=1280,1024")
    else:
        # If headless is required, we use these special flags
        args.append("--headless=new")
        args.append("--remote-debugging-port=9222")

    return args


def install_extension_in_context(context):
    """
    Install the extension in a browser context (not implemented yet, as this requires direct CDP access)

    Args:
        context: The browser context to install the extension in

    Returns:
        bool: Whether the installation was successful
    """
    # This is a placeholder for future implementation
    # Installing extensions in Playwright requires special handling
    logger.warning("Installing extensions in a context is not fully implemented yet")
    return False


def create_temp_extension_dir() -> str:
    """
    Create a temporary directory with the extension files
    This is useful for scenarios where we need a unique path for each browser instance

    Returns:
        str: Path to the temporary extension directory
    """
    source_dir = get_extension_path()
    if not source_dir:
        return ""

    # Create a temporary directory
    temp_dir = tempfile.mkdtemp(prefix="workflow_recorder_ext_")

    try:
        # Copy extension files
        for item in os.listdir(source_dir):
            source_item = os.path.join(source_dir, item)
            dest_item = os.path.join(temp_dir, item)

            if os.path.isdir(source_item):
                shutil.copytree(source_item, dest_item)
            else:
                shutil.copy2(source_item, dest_item)

        logger.info(f"Created temporary extension directory: {temp_dir}")
        return temp_dir
    except Exception as e:
        logger.error(f"Failed to create temporary extension directory: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return ""
