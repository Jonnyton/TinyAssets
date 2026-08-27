## ADDED Requirements

### Requirement: Daemon image GitHub CLI selection is exact and signed
The daemon image build SHALL install GitHub CLI from the configured GitHub-signed apt repository at an explicit package version and SHALL fail before image publication when that exact version is unavailable.

#### Scenario: Exact signed package is available
- **WHEN** the configured signed repository publishes the Dockerfile's exact GitHub CLI version
- **THEN** the image installs that exact package and continues the build

#### Scenario: Exact package has expired from the repository
- **WHEN** the configured signed repository no longer publishes the Dockerfile's exact GitHub CLI version
- **THEN** the build fails visibly before publishing an image or triggering production deployment
