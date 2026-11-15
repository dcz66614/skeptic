# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in Skeptic, please do not disclose it publicly.

GitHub Private Vulnerability Reporting will be enabled once the public repository is created (pending human release gate R81). Once enabled, please submit vulnerability reports via GitHub's private vulnerability reporting interface on the repository's Security tab.

When reporting, please include:
- A description of the vulnerability and its potential impact.
- Steps to reproduce or proof-of-concept code.
- Any suggested fixes or mitigations.

## Responsible Use

Skeptic is designed as a local resilience, chaos-engineering, and evaluation tool for Model Context Protocol (MCP) tool-using agents and environments that the operator directly owns, manages, or controls.

- **Authorized Scope**: Use Skeptic solely against agents, MCP servers, and systems you have explicit authorization to test.
- **No Attack Tool**: Skeptic's fault-injection, adversarial simulation (e.g. prompt injection checks, rug pull, description poisoning), and chaos mechanisms are intended exclusively to measure and harden an agent's skepticism and recoverability. They do not constitute permission or tooling to attack third-party systems, exfiltrate data, bypass authorization boundaries, or compromise unauthorized infrastructure.
- **Synthetic Canaries**: Any canary tokens or simulated injection payloads supplied in default scenarios/tests are strictly synthetic test fixtures. Never deploy live production secrets or tokens into benchmark scenarios or cassette recordings.
