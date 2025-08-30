# Contributing to semantic-copycat-oslili

Thank you for your interest in contributing to semantic-copycat-oslili! This document provides guidelines for contributing to the project.

## Development Workflow

### Pull Request Requirement

**All changes MUST go through a Pull Request.** Direct commits to the main branch are not allowed. This includes:

- 🐛 Bug fixes and hotfixes
- ✨ New features
- 📝 Documentation updates
- ⚙️ Configuration changes
- 🔖 Version bumps
- 📄 License updates

This ensures:
- Proper tracking of all changes
- Opportunity for code review
- Ability to rollback if issues are discovered
- Clean git history

### Creating a Pull Request

1. **Fork or branch from main**
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**
   - Write clean, readable code
   - Follow existing code style
   - Add tests if applicable
   - Update documentation

3. **Commit with clear messages**
   ```bash
   git add .
   git commit -m "type: Brief description
   
   Detailed explanation if needed"
   ```

   Commit types:
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `test:` Test additions or changes
   - `chore:` Maintenance tasks
   - `refactor:` Code refactoring

4. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then create a PR on GitHub with a clear description.

## Development Setup

### Prerequisites

- Python 3.8 or higher
- pip package manager
- git

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/oscarvalenzuelab/semantic-copycat-oslili.git
   cd semantic-copycat-oslili
   ```

2. **Install in development mode**
   ```bash
   pip install -e .[dev]
   ```

3. **Install pre-commit hooks (optional)**
   ```bash
   pre-commit install
   ```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=semantic_copycat_oslili

# Run specific test file
pytest tests/test_license_detector.py
```

### Testing CLI

```bash
# Test from source
python -m semantic_copycat_oslili.cli --help

# Test specific features
python -m semantic_copycat_oslili.cli /path/to/project -f kissbom
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Maximum line length: 100 characters
- Use descriptive variable names
- Add docstrings to all public functions

### Running Code Formatters

```bash
# Format with black
black semantic_copycat_oslili/

# Sort imports
isort semantic_copycat_oslili/

# Check style
flake8 semantic_copycat_oslili/
```

## Testing Guidelines

- Write tests for new features
- Maintain or improve code coverage
- Test edge cases
- Use meaningful test names

## Documentation

### Updating Documentation

- Update README.md for user-facing changes
- Update API.md for API changes
- Update USAGE.md for new examples
- Add docstrings to new functions
- Update CHANGELOG.md for all changes

### SPDX License Data

To update the bundled SPDX license data:

```bash
python scripts/download_spdx_licenses.py
```

See `docs/SPDX.md` for detailed instructions.

## Versioning

We follow [Semantic Versioning](https://semver.org/):
- MAJOR version for incompatible API changes
- MINOR version for backwards-compatible functionality additions
- PATCH version for backwards-compatible bug fixes

Version updates should be made in:
- `pyproject.toml`
- `semantic_copycat_oslili/__init__.py`
- `CHANGELOG.md`

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

## Questions?

If you have questions, please open an issue on GitHub.