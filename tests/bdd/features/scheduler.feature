Feature: Annual tax data maintenance
  As a system administrator
  I want the tax data to be updated each year
  So that taxpayers always see accurate, current rates

  Background:
    Given the nexus-tax service is running with 2024 data

  Scenario: Admin can manually seed a new tax year (mirrors annual scheduler)
    When I trigger a seed for tax year 2025 as admin
    Then the tax year 2025 period should exist
    And the 2025 rate bundle should contain brackets

  Scenario: Seeding is idempotent — re-seeding the same year is safe
    When I trigger a seed for tax year 2024 as admin
    Then the response should indicate success
    And the 2024 data should still be intact
