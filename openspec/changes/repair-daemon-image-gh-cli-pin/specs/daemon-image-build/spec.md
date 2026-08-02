## ADDED Requirements

### Requirement: Daemon image dependencies are exact and signed
The daemon image build SHALL install GitHub CLI from the configured GitHub-signed apt repository at an explicit package version and SHALL fail before image publication when that exact version is unavailable.

#### Scenario: Exact signed package is available
- **WHEN** the configured signed repository publishes the Dockerfile's exact GitHub CLI version
- **THEN** the image installs that exact package and continues the build

#### Scenario: Exact package has expired from the repository
- **WHEN** the configured signed repository no longer publishes the Dockerfile's exact GitHub CLI version
- **THEN** the build fails visibly before publishing an image or triggering production deployment

### Requirement: Production deploys only a successfully built main image
The release chain SHALL deploy the exact merged-main image only after its image build succeeds and SHALL require the production public canary to pass before the release is accepted.

#### Scenario: Image build succeeds
- **WHEN** the exact merged-main image builds and publishes successfully
- **THEN** the production workflow may deploy that exact image and runs the public MCP canary

#### Scenario: Image build fails
- **WHEN** dependency resolution or any other image-build step fails
- **THEN** no image from that run is published or admitted to production deployment
