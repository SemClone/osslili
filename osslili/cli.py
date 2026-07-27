"""
CLI interface for osslili.
"""

import sys
import logging
from pathlib import Path
from typing import Optional

import click
import yaml
from colorama import init, Fore, Style

from . import __version__
from .core.models import SCAN_MODES, Config
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


def resolve_scan_mode(scan_mode: Optional[str], deep: bool,
                      license_files_only: bool) -> Optional[str]:
    """Resolve the scanning mode from --scan-mode and its legacy flag aliases.

    Returns None when no mode was requested, leaving the configured default in
    place. Contradictory requests are a usage error rather than a silent pick.
    """
    aliases = []
    if deep:
        aliases.append(('deep', '--deep'))
    if license_files_only:
        aliases.append(('license-files', '--license-files-only'))

    if len(aliases) > 1:
        raise click.UsageError(
            f"{aliases[0][1]} and {aliases[1][1]} select different scanning modes; use one"
        )
    if scan_mode and aliases and scan_mode != aliases[0][0]:
        raise click.UsageError(
            f"--scan-mode {scan_mode} conflicts with {aliases[0][1]}; use one"
        )

    if scan_mode:
        return scan_mode
    return aliases[0][0] if aliases else None


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
    default=4,
    help='Number of processing threads (default: 4)'
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
    default=4,
    help='Maximum directory recursion depth (default: 4, use -1 for unlimited)'
)
@click.option(
    '--max-extraction-depth',
    type=int,
    default=10,
    help='Maximum archive extraction depth (default: 10)'
)
@click.option(
    '--evidence-detail', '--detail',
    type=click.Choice(['minimal', 'summary', 'detailed', 'full']),
    default='detailed',
    help='Evidence detail level: minimal (license summary only), summary (per-method counts), detailed (sample detections), full (all detections)'
)
@click.option(
    '--skip-content-detection',
    is_flag=True,
    help='Skip content-based file type detection (faster, less thorough)'
)
@click.option(
    '--license-files-only',
    is_flag=True,
    help='Strictly scan only LICENSE files (excludes metadata and README). Alias for --scan-mode license-files.'
)
@click.option(
    '--scan-mode', '--mode', 'scan_mode',
    type=click.Choice(SCAN_MODES),
    default=None,
    help='Scanning mode preset: default (license files, metadata, docs), deep (all files), '
         'license-files (LICENSE files only), lightweight (all files, no package metadata, '
         'no full text comparison)'
)
@click.option(
    '--license-files/--no-license-files', 'scan_license_files',
    default=None,
    help='Scan the project\'s own LICENSE/COPYING files (default: enabled)'
)
@click.option(
    '--notice-files/--no-notice-files', 'scan_notice_files',
    default=None,
    help='Scan bundled third-party notice files (default: enabled)'
)
@click.option(
    '--package-metadata/--no-package-metadata', 'scan_package_metadata',
    default=None,
    help='Scan package metadata such as package.json or pom.xml (default: enabled). '
         'Disable when declared licenses come from a package metadata analyzer'
)
@click.option(
    '--documentation/--no-documentation', 'scan_documentation',
    default=None,
    help='Scan README and other readable documentation (default: enabled)'
)
@click.option(
    '--source-files/--no-source-files', 'scan_source_files',
    default=None,
    help='Scan all other readable files for embedded licenses (default: enabled in deep '
         'and lightweight modes only)'
)
@click.option(
    '--text-similarity/--no-text-similarity', 'text_similarity',
    default=None,
    help='Compare file contents against full SPDX license texts (default: enabled). '
         'Disabling leaves SPDX tags, keywords and references, which is much faster'
)
@click.option(
    '--skip-extensionless',
    is_flag=True,
    help='Skip files without extensions unless they match known patterns'
)
@click.option(
    '--max-file-size',
    type=int,
    help='Skip files larger than this size in KB'
)
@click.option(
    '--skip-smart-read',
    is_flag=True,
    help='Read files sequentially instead of sampling start/end'
)
@click.option(
    '--fast',
    is_flag=True,
    help='Enable fast mode preset (combines multiple optimizations)'
)
@click.option(
    '--deep',
    is_flag=True,
    help='Enable comprehensive scan of all source files (slower, more thorough). Alias for --scan-mode deep.'
)
@click.version_option(version=__version__, prog_name='osslili')
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
    max_extraction_depth: Optional[int],
    evidence_detail: str,
    skip_content_detection: bool,
    license_files_only: bool,
    scan_mode: Optional[str],
    scan_license_files: Optional[bool],
    scan_notice_files: Optional[bool],
    scan_package_metadata: Optional[bool],
    scan_documentation: Optional[bool],
    scan_source_files: Optional[bool],
    text_similarity: Optional[bool],
    skip_extensionless: bool,
    max_file_size: Optional[int],
    skip_smart_read: bool,
    fast: bool,
    deep: bool
):
    """
    Scan local source code for license and copyright information.

    INPUT can be:
    - A local directory to scan recursively
    - A local file to analyze

    By default, scans LICENSE files, package metadata (package.json, setup.py, etc.),
    and README files for fast results. Use --deep for comprehensive source code scanning,
    or --scan-mode lightweight to scan all files with cheap detection and no package
    metadata. Modes are presets over the individual scan targets (--license-files,
    --notice-files, --package-metadata, --documentation, --source-files), each of which
    can be turned on or off on top of the selected mode.

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

    # Performance optimization flags
    if fast:
        cfg.fast_mode = True
        cfg.apply_fast_mode()
    # Scanning mode preset. --deep and --license-files-only are aliases for the
    # corresponding modes, kept for compatibility.
    mode = resolve_scan_mode(scan_mode, deep=deep, license_files_only=license_files_only)
    if mode:
        cfg.apply_scan_mode(mode)

    # Individual scan targets override whatever the mode selected
    if scan_license_files is not None:
        cfg.scan_license_files = scan_license_files
    if scan_notice_files is not None:
        cfg.scan_notice_files = scan_notice_files
    if scan_package_metadata is not None:
        cfg.scan_package_metadata = scan_package_metadata
    if scan_documentation is not None:
        cfg.scan_documentation = scan_documentation
    if scan_source_files is not None:
        cfg.scan_source_files = scan_source_files
    if text_similarity is not None:
        cfg.text_similarity_matching = text_similarity

    if skip_content_detection:
        cfg.skip_content_detection = True
    if skip_extensionless:
        cfg.skip_extensionless = True
    if max_file_size is not None:
        cfg.max_file_size_kb = max_file_size
    if skip_smart_read:
        cfg.skip_smart_read = True
    
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
            output_data = detector.generate_evidence(results, detail_level=evidence_detail)
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