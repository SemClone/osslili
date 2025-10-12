"""
CLI interface for semantic-copycat-oslili.
"""

import sys
import logging
from pathlib import Path
from typing import Optional

import click
import yaml
from colorama import init, Fore, Style

from . import __version__
from .core.models import Config
from .core.generator import LicenseCopyrightDetector
from .utils.logging import setup_logging

init(autoreset=True)


def print_success(message: str):
    """Print success message in green."""
    click.echo(f"{Fore.GREEN}✓ {message}{Style.RESET_ALL}")


def print_error(message: str):
    """Print error message in red."""
    click.echo(f"{Fore.RED}✗ {message}{Style.RESET_ALL}", err=True)


def print_warning(message: str):
    """Print warning message in yellow."""
    click.echo(f"{Fore.YELLOW}⚠ {message}{Style.RESET_ALL}")


def print_info(message: str):
    """Print info message in blue."""
    click.echo(f"{Fore.BLUE}ℹ {message}{Style.RESET_ALL}")


def load_config(config_path: Optional[str]) -> Config:
    """Load configuration from file if provided."""
    if not config_path:
        return Config()
    
    try:
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        config = Config()
        for key, value in config_data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        
        print_info(f"Loaded configuration from {config_path}")
        return config
    except Exception as e:
        print_warning(f"Failed to load config from {config_path}: {e}")
        return Config()


def detect_input_type(input_path: str) -> str:
    """Detect whether input is a file or directory."""
    path = Path(input_path)
    if path.exists():
        if path.is_file():
            return "local_file"
        elif path.is_dir():
            return "local_dir"
    
    # Path doesn't exist
    return "invalid"


@click.command()
@click.argument('input_path', type=str)
@click.option(
    '--output', '-o',
    type=click.Path(),
    help='Output file path (default: stdout)'
)
@click.option(
    '--output-format', '-f',
    type=click.Choice(['evidence', 'kissbom', 'cyclonedx-json', 'cyclonedx-xml']),
    default='evidence',
    help='Output format (default: evidence)'
)
@click.option(
    '--verbose', '-v',
    is_flag=True,
    help='Enable verbose logging'
)
@click.option(
    '--debug', '-d',
    is_flag=True,
    help='Enable debug logging'
)
@click.option(
    '--threads', '-t',
    type=int,
    help='Number of processing threads'
)
@click.option(
    '--config', '-c',
    type=click.Path(exists=True),
    help='Path to configuration file'
)
@click.option(
    '--similarity-threshold',
    type=float,
    help='License similarity threshold (0.0-1.0)'
)
@click.option(
    '--max-depth', '--max-recursion-depth',
    type=int,
    default=10,
    help='Maximum directory recursion depth (default: 10, use -1 for unlimited)'
)
@click.option(
    '--max-extraction-depth',
    type=int,
    default=10,
    help='Maximum archive extraction depth (default: 10)'
)
@click.version_option(version=__version__, prog_name='oslili')
def main(
    input_path: str,
    output: Optional[str],
    output_format: str,
    verbose: bool,
    debug: bool,
    threads: Optional[int],
    config: Optional[str],
    similarity_threshold: Optional[float],
    max_depth: Optional[int],
    max_extraction_depth: Optional[int]
):
    """
    Scan local source code for license and copyright information.
    
    INPUT can be:
    - A local directory to scan recursively
    - A local file to analyze
    
    The tool performs:
    - SPDX license identification using regex and fuzzy hashing
    - Copyright information extraction
    - License file detection and matching
    """
    
    # Load configuration
    cfg = load_config(config)
    
    # Override config with CLI options
    if verbose:
        cfg.verbose = True
    if debug:
        cfg.debug = True
    if threads is not None:
        cfg.thread_count = threads
    if similarity_threshold is not None:
        cfg.similarity_threshold = similarity_threshold
    if max_depth is not None:
        cfg.max_recursion_depth = max_depth
    if max_extraction_depth is not None:
        cfg.max_extraction_depth = max_extraction_depth
    
    # Setup logging - only show our logs in verbose mode, not library logs
    if cfg.debug:
        log_level = logging.DEBUG
    elif cfg.verbose:
        log_level = logging.INFO
    else:
        log_level = logging.ERROR  # Suppress all but errors in normal mode
    
    setup_logging(log_level)
    
    # Additional suppression of warnings
    import warnings
    warnings.filterwarnings('ignore', category=UserWarning)
    if not cfg.debug:
        # Suppress urllib3 warnings about SSL
        import urllib3
        urllib3.disable_warnings()
        # Specifically suppress the NotOpenSSLWarning
        from urllib3.exceptions import NotOpenSSLWarning
        warnings.filterwarnings('ignore', category=NotOpenSSLWarning)
    
    # Detect input type
    input_type = detect_input_type(input_path)
    
    if cfg.verbose:
        print_info(f"Detected input type: {input_type}")
    
    try:
        # Initialize detector
        detector = LicenseCopyrightDetector(cfg)
        
        # Process input based on type
        results = []
        
        if input_type in ["local_file", "local_dir"]:
            print_info(f"Processing local path: {input_path}")
            result = detector.process_local_path(input_path)
            results = [result]
        elif input_type == "invalid":
            print_error(f"Path does not exist: {input_path}")
            sys.exit(1)
        else:
            print_error(f"Unknown input type: {input_type}")
            sys.exit(1)
        
        # Check for errors
        total_errors = sum(len(r.errors) for r in results)
        if total_errors > 0:
            print_warning(f"Encountered {total_errors} errors during processing")
        
        # Generate output based on format
        if output_format == 'evidence':
            output_data = detector.generate_evidence(results)
        elif output_format == 'kissbom':
            output_data = detector.generate_kissbom(results)
        elif output_format == 'cyclonedx-json':
            output_data = detector.generate_cyclonedx(results, format_type='json')
        elif output_format == 'cyclonedx-xml':
            output_data = detector.generate_cyclonedx(results, format_type='xml')
        else:
            output_data = detector.generate_evidence(results)
        
        # Write output
        if output:
            with open(output, 'w') as f:
                f.write(output_data)
            print_success(f"Detection results written to {output}")
        else:
            click.echo(output_data)
        
        # Summary
        if cfg.verbose:
            print_success(f"Processed {len(results)} package(s)")
            licenses_found = sum(len(r.licenses) for r in results)
            copyrights_found = sum(len(r.copyrights) for r in results)
            print_info(f"Found {licenses_found} license(s) and {copyrights_found} copyright statement(s)")
    
    except KeyboardInterrupt:
        print_error("Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"Fatal error: {e}")
        if cfg.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()