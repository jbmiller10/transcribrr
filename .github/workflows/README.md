# GitHub Actions Workflows

This directory contains the CI/CD workflows for the Transcribrr project. These workflows automate testing, building, releasing, and maintaining code quality.

## Workflows Overview

### 1. CI/CD Pipeline (`ci.yml`)

**Trigger:** Push to main, Pull Requests, Manual dispatch

**Purpose:** Main continuous integration pipeline that ensures code quality and functionality.

**Jobs:**
- **Lint:** Code quality checks using Ruff and MyPy
- **Test:** Unit test suite with coverage reporting
  - Matrix testing: Python 3.11 and 3.12 on Ubuntu, macOS, and Windows
  - Handles GUI mocking for headless environments
  - Generates coverage reports
- **Integration Test:** Runs integration tests in isolated environment
- **Build:** Verifies package can be built with Briefcase
- **Security Scan:** Checks for security vulnerabilities using Safety and Bandit

**Key Features:**
- Dependency caching for faster builds
- Parallel job execution where possible
- Cross-platform testing
- Coverage reporting with PR comments
- Graceful handling of optional dependencies (PyQt6, torch)

### 2. Release Pipeline (`release.yml`)

**Trigger:** Version tags (v*), Manual dispatch

**Purpose:** Automates the release process for new versions.

**Jobs:**
- **Build and Test:** Creates platform-specific builds
  - macOS (.dmg)
  - Windows (.msi)
  - Linux (.AppImage, .deb)
- **Create Release:** Generates GitHub release with artifacts
- **Update Homebrew:** Updates Homebrew formula (macOS only)

**Key Features:**
- Multi-platform build support
- Automatic version detection from tags
- Release notes generation
- Checksum calculation for artifacts
- Pre-release support

### 3. Dependency Management (`dependencies.yml`)

**Trigger:** Weekly schedule (Mondays 3 AM UTC), Manual dispatch

**Purpose:** Keeps dependencies up-to-date and secure.

**Jobs:**
- **Check Dependencies:** 
  - Security vulnerability scanning
  - Outdated package detection
  - Dependency tree visualization
- **Audit Licenses:** Ensures license compliance

**Key Features:**
- Automatic PR creation for updates
- Security-first update strategy
- License compliance checking
- Configurable update types (security, patch, minor, major)

### 4. Code Quality & Performance (`quality.yml`)

**Trigger:** Pull Requests, Push to main, Manual dispatch

**Purpose:** Advanced code quality analysis and performance monitoring.

**Jobs:**
- **Code Quality Analysis:**
  - Pylint scoring
  - Flake8 style checking
  - Cyclomatic complexity analysis
  - Dead code detection
  - Documentation coverage
- **Performance Profiling:**
  - Memory usage profiling
  - Import time analysis
  - Object creation benchmarks
- **Type Checking:**
  - MyPy strict mode
  - Pyright analysis

**Key Features:**
- Comprehensive quality metrics
- Performance baseline tracking
- Multiple static analysis tools
- Quality score calculation

## Configuration

### Required Secrets

No additional secrets required - workflows use the default `GITHUB_TOKEN`.

### Environment Variables

Workflows use these environment variables:
- `PYTHON_VERSION`: Default Python version (3.11)
- `QT_QPA_PLATFORM`: Set to 'offscreen' for headless GUI testing
- `DISPLAY`: Virtual display for X11 applications
- `TRANSCRIBRR_TEST_MODE`: Enables test mode for the application

## Usage

### Running Tests Locally

To replicate CI testing locally:

```bash
# Set up environment
export QT_QPA_PLATFORM=offscreen
export TRANSCRIBRR_TEST_MODE=1

# Run unit tests
python -m unittest discover -s app/tests -p "test_*.py" -v

# Generate coverage
python -m coverage run -m unittest discover -s app/tests
python -m coverage report
```

### Manual Workflow Triggers

You can manually trigger workflows from the GitHub Actions tab:

1. Go to Actions tab in your repository
2. Select the workflow you want to run
3. Click "Run workflow"
4. Fill in any required inputs
5. Click "Run workflow" button

### Creating a Release

1. Tag your commit:
   ```bash
   git tag -a v1.0.1 -m "Release version 1.0.1"
   git push origin v1.0.1
   ```

2. The release workflow will automatically:
   - Build for all platforms
   - Create GitHub release
   - Upload artifacts

### Dependency Updates

The dependency workflow runs weekly but can be triggered manually:
1. Go to Actions → Dependency Management
2. Run workflow with desired update type
3. Review and merge the created PR

## Troubleshooting

### Common Issues

1. **GUI Tests Failing:**
   - Ensure `QT_QPA_PLATFORM=offscreen` is set
   - Check virtual display setup for Linux

2. **Dependency Conflicts:**
   - Check `requirements-ci.txt` for CI-specific deps
   - Some packages (PyQt6, torch) are skipped in CI

3. **Build Failures:**
   - Verify Briefcase configuration in `pyproject.toml`
   - Check platform-specific requirements

4. **Coverage Not Reported:**
   - Ensure tests are discovered correctly
   - Check coverage omit patterns

### Workflow Debugging

Enable debug logging:
1. Go to Settings → Secrets and variables → Actions
2. Add repository variable: `ACTIONS_STEP_DEBUG` = `true`
3. Add repository variable: `ACTIONS_RUNNER_DEBUG` = `true`

## Best Practices

1. **Keep workflows DRY:** Use composite actions for repeated steps
2. **Cache aggressively:** Cache dependencies, build artifacts
3. **Fail fast:** Use `fail-fast: false` only when needed
4. **Set timeouts:** Prevent hung jobs from consuming minutes
5. **Use matrix builds:** Test across multiple configurations
6. **Monitor usage:** Check Actions usage in Settings → Billing

## Customization

To customize workflows for your needs:

1. **Python versions:** Edit `matrix.python-version` in `ci.yml`
2. **Test patterns:** Modify test discovery patterns
3. **Quality thresholds:** Adjust complexity limits in `quality.yml`
4. **Release platforms:** Configure `matrix.include` in `release.yml`
5. **Update schedule:** Change cron expression in `dependencies.yml`

## Contributing

When modifying workflows:
1. Test changes in a feature branch first
2. Use `workflow_dispatch` for testing
3. Verify all jobs pass before merging
4. Update this README if adding new workflows