Feature: Tax bracket retrieval and calculation
  As a developer or end user
  I want to look up tax brackets and calculate federal taxes
  So I can understand tax liabilities

  Background:
    Given the nexus-tax service is running with 2024 data

  Scenario: Get rate bundle for 2024
    When I request the rate bundle for year 2024
    Then the response includes brackets
    And the response includes standard_deductions
    And the response includes special_rates

  Scenario: Calculate tax for a single filer with $50,000 income
    When I calculate tax for income=50000 filing_status="single" year=2024
    Then the response tax_year is 2024
    And the response standard_deduction is 14600.0
    And the response taxable_income is 35400.0
    And the response marginal_rate is 0.12

  Scenario: Calculate tax for MFJ filer with $100,000 income
    When I calculate tax for income=100000 filing_status="mfj" year=2024
    Then the response standard_deduction is 29200.0
    And the response taxable_income is 70800.0

  Scenario: Invalid filing status returns 422
    When I calculate tax with invalid filing_status "xyz"
    Then the response status code is 422

  Scenario: Unseeded year returns 404
    When I calculate tax for income=50000 filing_status="single" year=1990
    Then the response status code is 404
