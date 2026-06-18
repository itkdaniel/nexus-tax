Feature: Questionnaire session flow
  As a taxpayer
  I want to complete a questionnaire
  So I know which tax forms I need to file

  Background:
    Given the nexus-tax service is running with 2024 data

  Scenario: Individual with W-2 income completes the questionnaire
    Given I start a new session for tax year 2024 as "individual"
    When I answer "entity_type" with "individual"
    And I answer "has_w2" with "yes"
    And I answer "filing_status" with "single"
    And I complete the session
    Then the required forms should include "1040"
    And the required forms should include "W-2"
    And the session status should be "completed"

  Scenario: Self-employed taxpayer gets Schedule C and SE
    Given I start a new session for tax year 2024 as "individual"
    When I answer "entity_type" with "individual"
    And I answer "has_self_employment" with "yes"
    And I complete the session
    Then the required forms should include "Schedule C"
    And the required forms should include "Schedule SE"

  Scenario: Partial answers are merged correctly
    Given I start a new session for tax year 2024 as "individual"
    When I answer "entity_type" with "individual"
    And I save answers incrementally with "has_w2" = "yes"
    And I save answers incrementally with "has_rental_income" = "yes"
    Then the session answers should contain both keys

  Scenario: Completed session cannot be updated
    Given I start a new session for tax year 2024 as "individual"
    When I answer "entity_type" with "individual"
    And I complete the session
    Then updating answers should return HTTP 409
