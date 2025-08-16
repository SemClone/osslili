"""
CLI interface for semantic-copycat-oslili.
"""

import sys
import logging
import json
from pathlib import Path
from typing import Optional, List

import click
import yaml
from colorama import init, Fore, Style

from .core.models import Config, OutputFormat
from .core.generator import LegalAttributionGenerator
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
    """Detect whether input is a purl, file, or directory."""
    # Check if it's a purl
    if input_path.startswith("pkg:"):
        return "purl"
    
    # Check if it's a file or directory
    path = Path(input_path)
    if path.exists():
        if path.is_file():
            # Check if it's a purl list file
            try:
                with open(path, 'r') as f:
                    first_line = f.readline().strip()
                    if first_line.startswith("pkg:") or first_line.startswith("#"):
                        return "purl_file"
            except:
                pass
            return "local_file"
        elif path.is_dir():
            return "local_dir"
    
    # Default to treating as purl if not a valid path
    return "purl"


@click.command()
@click.argument('input_path', type=str)
@click.option(
    '--output-format', '-f',
    type=click.Choice(['kissbom', 'cyclonedx-json', 'cyclonedx-xml', 'notices']),
    default='kissbom',
    help='Output format for attribution data'
)
@click.option(
    '--output', '-o',
    type=click.Path(),
    help='Output file path (default: stdout)'
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
    '--max-depth',
    type=int,
    help='Maximum archive extraction depth'
)
@click.option(
    '--timeout',
    type=int,
    help='Network request timeout in seconds'
)
@click.option(
    '--online',
    is_flag=True,
    help='Enable external API sources (ClearlyDefined, PyPI, npm) to supplement local analysis'
)
def main(
    input_path: str,
    output_format: str,
    output: Optional[str],
    verbose: bool,
    debug: bool,
    threads: Optional[int],
    config: Optional[str],
    similarity_threshold: Optional[float],
    max_depth: Optional[int],
    timeout: Optional[int],
    online: bool
):
    """
    Generate legal attribution notices from software packages.
    
    INPUT can be:
    - A package URL (purl) like pkg:pypi/requests@2.28.1
    - A file containing multiple purls (one per line)
    - A local directory or file path to analyze
    
    By default, the tool works offline, downloading and analyzing packages locally.
    Use --online to enable external API sources (ClearlyDefined, PyPI, npm) for
    supplemental license and copyright data.
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
        cfg.max_extraction_depth = max_depth
    if timeout is not None:
        cfg.network_timeout = timeout
    
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
        print_info(f"Output format: {output_format}")
    
    try:
        # Initialize generator
        generator = LegalAttributionGenerator(cfg)
        
        # Process input based on type
        results = []
        
        if input_type == "purl":
            mode_str = "(online mode)" if online else "(offline mode)"
            print_info(f"Processing package URL: {input_path} {mode_str}")
            result = generator.process_purl(input_path, use_external_sources=online)
            results = [result]
            
        elif input_type == "purl_file":
            mode_str = "(online mode)" if online else "(offline mode)"
            print_info(f"Processing purl list from: {input_path} {mode_str}")
            # Process each purl with the online flag
            with open(input_path, 'r') as f:
                purls = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
            results = []
            for purl in purls:
                result = generator.process_purl(purl, use_external_sources=online)
                results.append(result)
            
        elif input_type in ["local_file", "local_dir"]:
            print_info(f"Processing local path: {input_path}")
            result = generator.process_local_path(input_path)
            results = [result]
        
        # Check for errors
        total_errors = sum(len(r.errors) for r in results)
        if total_errors > 0:
            print_warning(f"Encountered {total_errors} errors during processing")
        
        # Generate output based on format
        output_data = None
        
        if output_format == "kissbom":
            output_data = json.dumps(generator.generate_kissbom(results), indent=2)
        elif output_format == "cyclonedx-json":
            output_data = generator.generate_cyclonedx(results, format="json")
        elif output_format == "cyclonedx-xml":
            output_data = generator.generate_cyclonedx(results, format="xml")
        elif output_format == "notices":
            output_data = generator.generate_notices(results)
        
        # Write output
        if output:
            with open(output, 'w') as f:
                f.write(output_data)
            print_success(f"Attribution data written to {output}")
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