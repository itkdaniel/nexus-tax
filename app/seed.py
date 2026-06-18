"""
Seed data for nexus-tax — mirrors server/tax-seed.ts exactly.

Idempotent: each function checks whether data already exists before inserting.
Call seed_tax_data(year) to run the full seeding sequence for a given year.

Seeding order (matches TypeScript):
  1. seed_tax_period(year)
  2. seed_federal_forms()
  3. seed_state_forms()
  4. seed_tax_brackets(year)
  5. seed_standard_deductions(year)
  6. seed_special_rates(year)
  7. seed_questions()
  8. seed_form_rules()
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import get_db
from app.models import (
    FederalFormModel,
    FormRequirementRuleModel,
    QuestionnaireSessionModel,
    SpecialTaxRateModel,
    StandardDeductionModel,
    StateFormModel,
    TaxBracketModel,
    TaxPeriodModel,
    TaxQuestionModel,
)


# ── 1. Tax Periods ────────────────────────────────────────────────────────────

async def seed_tax_period(tax_year: int) -> None:
    async with get_db() as db:
        existing = (await db.execute(
            select(TaxPeriodModel).where(TaxPeriodModel.tax_year == tax_year)
        )).scalar_one_or_none()
        if existing:
            return

        filing_year = tax_year + 1
        status = "active" if tax_year >= datetime.now(timezone.utc).year - 1 else "closed"
        period = TaxPeriodModel(
            tax_year=tax_year,
            filing_deadline=f"April 15, {filing_year}",
            extension_deadline=f"October 15, {filing_year}",
            status=status,
            notes=None,
        )
        db.add(period)
    print(f"[tax-seed] Tax period {tax_year} seeded.")


# ── 2. Federal Forms ──────────────────────────────────────────────────────────

FEDERAL_FORMS = [
    # Core Individual Returns
    {"form_number": "1040", "sort_order": 1, "category": "individual", "title": "U.S. Individual Income Tax Return",
     "description": "The primary federal tax return for individual taxpayers. Reports income, deductions, credits, and calculates tax owed or refund due.",
     "who_files": "Taxpayer", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040gi"},
    {"form_number": "1040-SR", "sort_order": 2, "category": "individual", "title": "U.S. Tax Return for Seniors",
     "description": "Simplified version of Form 1040 for taxpayers 65 and older. Same content as 1040 but with larger print and a standard deduction chart.",
     "who_files": "Taxpayer age 65+", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1040-sr",
     "instructions_url": "https://www.irs.gov/instructions/i1040sr"},
    {"form_number": "1040-NR", "sort_order": 3, "category": "individual", "title": "U.S. Nonresident Alien Income Tax Return",
     "description": "Required for nonresident aliens with U.S.-source income. Different deductions and rates than Form 1040.",
     "who_files": "Nonresident alien", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1040-nr",
     "instructions_url": "https://www.irs.gov/instructions/i1040nr"},
    {"form_number": "1040-X", "sort_order": 4, "category": "individual", "title": "Amended U.S. Individual Income Tax Return",
     "description": "Used to correct a previously filed Form 1040. Must be filed on paper (cannot e-file for most years).",
     "who_files": "Taxpayer correcting a prior return", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1040-x",
     "instructions_url": "https://www.irs.gov/instructions/i1040x"},
    {"form_number": "4868", "sort_order": 5, "category": "individual", "subcategory": "extension", "title": "Application for Automatic Extension of Time to File",
     "description": "Grants an automatic 6-month extension to file your tax return (to October 15). Does NOT extend time to pay taxes owed.",
     "who_files": "Taxpayer", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-4868",
     "instructions_url": "https://www.irs.gov/instructions/i4868"},
    # Schedules
    {"form_number": "Schedule A", "sort_order": 10, "category": "individual", "subcategory": "deduction", "title": "Itemized Deductions",
     "description": "Used to itemize deductions such as mortgage interest, state/local taxes (SALT, capped at $10,000), charitable contributions, and medical expenses.",
     "who_files": "Taxpayer who itemizes", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-a-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040sca"},
    {"form_number": "Schedule B", "sort_order": 11, "category": "individual", "subcategory": "income", "title": "Interest and Ordinary Dividends",
     "description": "Required when total taxable interest or ordinary dividends exceed $1,500, or when you have foreign accounts or trusts.",
     "who_files": "Taxpayer with interest/dividends > $1,500", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-b-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040sb"},
    {"form_number": "Schedule C", "sort_order": 12, "category": "individual", "subcategory": "income", "title": "Profit or Loss From Business",
     "description": "Reports income and expenses for sole proprietors and single-member LLCs. Net profit is subject to self-employment tax.",
     "who_files": "Sole proprietor / freelancer / single-member LLC", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-c-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040sc"},
    {"form_number": "Schedule D", "sort_order": 13, "category": "individual", "subcategory": "income", "title": "Capital Gains and Losses",
     "description": "Summarizes capital gains and losses from investment sales, including stocks, bonds, real estate, and cryptocurrency.",
     "who_files": "Taxpayer with capital gains/losses", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-d-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040sd"},
    {"form_number": "Schedule E", "sort_order": 14, "category": "individual", "subcategory": "income", "title": "Supplemental Income and Loss",
     "description": "Reports income/loss from rental real estate, royalties, partnerships, S corporations, trusts, and estates.",
     "who_files": "Taxpayer with rental income, K-1 income, etc.", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-e-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040se"},
    {"form_number": "Schedule SE", "sort_order": 15, "category": "individual", "subcategory": "employment", "title": "Self-Employment Tax",
     "description": "Calculates the self-employment tax (15.3%) owed by sole proprietors and freelancers for Social Security and Medicare coverage.",
     "who_files": "Self-employed individual with net SE income > $400", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-se-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040sse"},
    {"form_number": "Schedule 1", "sort_order": 16, "category": "individual", "subcategory": "income", "title": "Additional Income and Adjustments",
     "description": "Reports additional income (alimony, business income, capital gains) and adjustments to income (IRA deductions, student loan interest, SE tax deduction).",
     "who_files": "Taxpayer with additional income or above-the-line deductions", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-1-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040s1"},
    {"form_number": "Schedule 2", "sort_order": 17, "category": "individual", "subcategory": "payment", "title": "Additional Taxes",
     "description": "Reports additional taxes including AMT, self-employment tax, household employment taxes, and repayment of premium tax credit.",
     "who_files": "Taxpayer with AMT, SE tax, or other additional taxes", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-2-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040s2"},
    {"form_number": "Schedule 3", "sort_order": 18, "category": "individual", "subcategory": "credit", "title": "Additional Credits and Payments",
     "description": "Reports non-refundable credits (foreign tax, education, child/dependent care) and other payments (estimated taxes, excess SS withholding).",
     "who_files": "Taxpayer with additional credits", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-3-form-1040",
     "instructions_url": "https://www.irs.gov/instructions/i1040s3"},
    # Income Documents (Provided by Employers/Institutions)
    {"form_number": "W-2", "sort_order": 20, "category": "informational", "subcategory": "income", "title": "Wage and Tax Statement",
     "description": "Issued by your employer by January 31. Reports wages paid and taxes withheld. You receive copies B, C, and 2.",
     "who_files": "Employer", "provided_by": "Your employer",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-w-2",
     "instructions_url": "https://www.irs.gov/instructions/iw2g"},
    {"form_number": "1099-NEC", "sort_order": 21, "category": "informational", "subcategory": "income", "title": "Nonemployee Compensation",
     "description": "Issued by clients who paid you $600 or more for freelance or contract work. Replaces Box 7 of the old 1099-MISC.",
     "who_files": "Business paying an independent contractor", "provided_by": "Your client or payer",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-nec",
     "instructions_url": "https://www.irs.gov/instructions/i1099nec"},
    {"form_number": "1099-MISC", "sort_order": 22, "category": "informational", "subcategory": "income", "title": "Miscellaneous Income",
     "description": "Reports miscellaneous payments: rent, prizes, medical payments, crop insurance, royalties ($10+), and other income not covered by more specific forms.",
     "who_files": "Business making miscellaneous payments", "provided_by": "The payer",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-misc",
     "instructions_url": "https://www.irs.gov/instructions/i1099mec"},
    {"form_number": "1099-INT", "sort_order": 23, "category": "informational", "subcategory": "income", "title": "Interest Income",
     "description": "Issued by banks and financial institutions reporting interest of $10 or more paid during the year.",
     "who_files": "Bank or financial institution", "provided_by": "Your bank or lender",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-int",
     "instructions_url": "https://www.irs.gov/instructions/i1099int"},
    {"form_number": "1099-DIV", "sort_order": 24, "category": "informational", "subcategory": "income", "title": "Dividends and Distributions",
     "description": "Issued by brokerages and mutual funds reporting dividends and distributions of $10 or more.",
     "who_files": "Brokerage or mutual fund", "provided_by": "Your brokerage",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-div",
     "instructions_url": "https://www.irs.gov/instructions/i1099div"},
    {"form_number": "1099-B", "sort_order": 25, "category": "informational", "subcategory": "income", "title": "Proceeds from Broker and Barter Exchange Transactions",
     "description": "Reports proceeds from sales of stocks, bonds, mutual funds, and other securities. Includes cost basis information.",
     "who_files": "Broker or barter exchange", "provided_by": "Your brokerage",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-b",
     "instructions_url": "https://www.irs.gov/instructions/i1099b"},
    {"form_number": "1099-R", "sort_order": 26, "category": "informational", "subcategory": "income", "title": "Distributions From Pensions, Annuities, Retirement Plans",
     "description": "Issued by retirement plan administrators reporting distributions from 401(k)s, IRAs, pensions, and annuities.",
     "who_files": "Retirement plan administrator", "provided_by": "Your retirement plan administrator",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-r",
     "instructions_url": "https://www.irs.gov/instructions/i1099r"},
    {"form_number": "SSA-1099", "sort_order": 27, "category": "informational", "subcategory": "income", "title": "Social Security Benefit Statement",
     "description": "Issued by the Social Security Administration showing Social Security benefits paid during the year. Up to 85% may be taxable.",
     "who_files": "Social Security Administration", "provided_by": "Social Security Administration",
     "filing_methods": [],
     "irs_url": "https://www.ssa.gov/myaccount/replacement-SSA-1099.html",
     "instructions_url": "https://www.ssa.gov/myaccount/replacement-SSA-1099.html"},
    {"form_number": "1099-G", "sort_order": 28, "category": "informational", "subcategory": "income", "title": "Certain Government Payments",
     "description": "Reports unemployment compensation, state tax refunds (if you itemized last year), and other government payments.",
     "who_files": "Government agency", "provided_by": "Your state unemployment agency",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-g",
     "instructions_url": "https://www.irs.gov/instructions/i1099g"},
    {"form_number": "1099-SA", "sort_order": 29, "category": "informational", "subcategory": "income", "title": "Distributions From an HSA, Archer MSA, or Medicare Advantage MSA",
     "description": "Reports distributions from an HSA or Archer MSA during the year. Determines if distributions were used for qualified medical expenses.",
     "who_files": "HSA trustee/custodian", "provided_by": "Your HSA administrator",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1099-sa",
     "instructions_url": "https://www.irs.gov/instructions/i1099sa"},
    {"form_number": "1095-A", "sort_order": 30, "category": "informational", "subcategory": "healthcare", "title": "Health Insurance Marketplace Statement",
     "description": "Issued by Healthcare.gov or your state exchange. Reports Marketplace coverage and advance premium tax credit payments. Required to complete Form 8962.",
     "who_files": "Health Insurance Marketplace", "provided_by": "Healthcare.gov or your state exchange",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1095-a",
     "instructions_url": "https://www.irs.gov/instructions/i1095a"},
    # Credits
    {"form_number": "8812", "sort_order": 40, "category": "individual", "subcategory": "credit", "title": "Credits for Qualifying Children and Other Dependents",
     "description": "Calculates the Child Tax Credit ($2,000 per qualifying child) and the Additional Child Tax Credit (refundable portion up to $1,600 per child).",
     "who_files": "Taxpayer with qualifying children", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8812",
     "instructions_url": "https://www.irs.gov/instructions/i8812"},
    {"form_number": "2441", "sort_order": 41, "category": "individual", "subcategory": "credit", "title": "Child and Dependent Care Expenses",
     "description": "Claims credit for childcare expenses for children under 13 or a disabled dependent. Credit is 20%-35% of expenses (up to $3,000 for one / $6,000 for two+).",
     "who_files": "Taxpayer with childcare expenses", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-2441",
     "instructions_url": "https://www.irs.gov/instructions/i2441"},
    {"form_number": "8863", "sort_order": 42, "category": "individual", "subcategory": "credit", "title": "Education Credits",
     "description": "Claims the American Opportunity Tax Credit (up to $2,500) and Lifetime Learning Credit (up to $2,000) for qualified higher education expenses.",
     "who_files": "Taxpayer paying qualifying education expenses", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8863",
     "instructions_url": "https://www.irs.gov/instructions/i8863"},
    {"form_number": "8839", "sort_order": 43, "category": "individual", "subcategory": "credit", "title": "Qualified Adoption Expenses",
     "description": "Claims the Adoption Credit for qualified expenses paid to adopt an eligible child (up to $16,810 per child for 2024).",
     "who_files": "Taxpayer who adopted a child", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8839",
     "instructions_url": "https://www.irs.gov/instructions/i8839"},
    {"form_number": "8880", "sort_order": 44, "category": "individual", "subcategory": "credit", "title": "Credit for Qualified Retirement Savings Contributions",
     "description": "Claims the Saver's Credit for lower/middle income taxpayers contributing to IRAs or employer retirement plans (up to $1,000 / $2,000 MFJ).",
     "who_files": "Lower-income taxpayer contributing to retirement", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8880",
     "instructions_url": "https://www.irs.gov/instructions/i8880"},
    {"form_number": "8962", "sort_order": 45, "category": "individual", "subcategory": "credit", "title": "Premium Tax Credit (PTC)",
     "description": "Reconciles advance payments of the Premium Tax Credit for Marketplace health insurance. Required if you received advance PTC payments.",
     "who_files": "Taxpayer with Marketplace health insurance", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8962",
     "instructions_url": "https://www.irs.gov/instructions/i8962"},
    {"form_number": "5695", "sort_order": 46, "category": "individual", "subcategory": "credit", "title": "Residential Energy Credits",
     "description": "Claims the Residential Clean Energy Credit (30% for solar, wind, battery storage) and Energy Efficient Home Improvement Credit.",
     "who_files": "Homeowner with qualifying energy improvements", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-5695",
     "instructions_url": "https://www.irs.gov/instructions/i5695"},
    # Deductions / Adjustments
    {"form_number": "1098", "sort_order": 50, "category": "informational", "subcategory": "deduction", "title": "Mortgage Interest Statement",
     "description": "Issued by your lender showing mortgage interest paid ($600+). Required if you itemize and deduct mortgage interest on Schedule A.",
     "who_files": "Mortgage lender", "provided_by": "Your mortgage lender",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1098",
     "instructions_url": "https://www.irs.gov/instructions/i1098"},
    {"form_number": "1098-E", "sort_order": 51, "category": "informational", "subcategory": "deduction", "title": "Student Loan Interest Statement",
     "description": "Issued by your student loan servicer if you paid $600+ in student loan interest. Up to $2,500 of interest may be deductible.",
     "who_files": "Student loan servicer", "provided_by": "Your student loan servicer",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1098-e",
     "instructions_url": "https://www.irs.gov/instructions/i1098e"},
    {"form_number": "1098-T", "sort_order": 52, "category": "informational", "subcategory": "credit", "title": "Tuition Statement",
     "description": "Issued by your college or university showing tuition paid and scholarships received. Required to claim education credits (Form 8863).",
     "who_files": "College or university", "provided_by": "Your school",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1098-t",
     "instructions_url": "https://www.irs.gov/instructions/i1098t"},
    {"form_number": "8283", "sort_order": 53, "category": "individual", "subcategory": "deduction", "title": "Noncash Charitable Contributions",
     "description": "Documents noncash charitable contributions over $500. Donations over $5,000 require a qualified appraisal.",
     "who_files": "Taxpayer with noncash donations > $500", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8283",
     "instructions_url": "https://www.irs.gov/instructions/i8283"},
    # Health / Savings Accounts
    {"form_number": "8889", "sort_order": 60, "category": "individual", "subcategory": "deduction", "title": "Health Savings Accounts (HSAs)",
     "description": "Reports HSA contributions (deductible), distributions, and determines tax treatment. Required for anyone with HSA activity.",
     "who_files": "HSA account holder", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8889",
     "instructions_url": "https://www.irs.gov/instructions/i8889"},
    {"form_number": "5498-SA", "sort_order": 61, "category": "informational", "subcategory": "deduction", "title": "HSA, Archer MSA, or Medicare Advantage MSA Information",
     "description": "Issued by your HSA custodian showing contributions made. Informational only — keep for your records.",
     "who_files": "HSA custodian", "provided_by": "Your HSA administrator",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-5498-sa",
     "instructions_url": "https://www.irs.gov/instructions/i5498sa"},
    # Self-Employment
    {"form_number": "1040-ES", "sort_order": 70, "category": "individual", "subcategory": "payment", "title": "Estimated Tax for Individuals",
     "description": "Used to make quarterly estimated tax payments. Required if you expect to owe $1,000+ after withholding (common for self-employed taxpayers).",
     "who_files": "Taxpayer with income not subject to withholding", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1040-es",
     "instructions_url": "https://www.irs.gov/instructions/i1040es"},
    {"form_number": "8829", "sort_order": 71, "category": "individual", "subcategory": "deduction", "title": "Expenses for Business Use of Your Home",
     "description": "Calculates the home office deduction for self-employed individuals using the regular method. Requires exclusive and regular business use.",
     "who_files": "Self-employed taxpayer with home office", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8829",
     "instructions_url": "https://www.irs.gov/instructions/i8829"},
    {"form_number": "8995", "sort_order": 72, "category": "individual", "subcategory": "deduction", "title": "Qualified Business Income Deduction",
     "description": "Calculates the 20% Qualified Business Income (QBI) deduction for pass-through business income. For most taxpayers with simpler situations.",
     "who_files": "Taxpayer with qualified business income", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8995",
     "instructions_url": "https://www.irs.gov/instructions/i8995"},
    # Capital Gains / Investments
    {"form_number": "8949", "sort_order": 80, "category": "individual", "subcategory": "income", "title": "Sales and Other Dispositions of Capital Assets",
     "description": "Reports each individual capital asset sale (stocks, bonds, real estate, crypto). Totals flow to Schedule D.",
     "who_files": "Taxpayer who sold capital assets", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8949",
     "instructions_url": "https://www.irs.gov/instructions/i8949"},
    # Retirement
    {"form_number": "5329", "sort_order": 90, "category": "individual", "subcategory": "payment", "title": "Additional Taxes on Qualified Plans",
     "description": "Calculates the 10% additional tax on early retirement account withdrawals (before age 59½) unless an exception applies.",
     "who_files": "Taxpayer with early retirement withdrawal", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-5329",
     "instructions_url": "https://www.irs.gov/instructions/i5329"},
    {"form_number": "5498", "sort_order": 91, "category": "informational", "subcategory": "deduction", "title": "IRA Contribution Information",
     "description": "Issued by your IRA custodian showing contributions and fair market value. Sent after the filing deadline (May/June). Informational — keep for records.",
     "who_files": "IRA custodian", "provided_by": "Your IRA custodian",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-5498",
     "instructions_url": "https://www.irs.gov/instructions/i5498"},
    # Foreign
    {"form_number": "2555", "sort_order": 100, "category": "individual", "subcategory": "exclusion", "title": "Foreign Earned Income Exclusion",
     "description": "Claims the Foreign Earned Income Exclusion (up to $126,500 for 2024) and/or Foreign Housing Exclusion for taxpayers living abroad.",
     "who_files": "U.S. citizen or resident living abroad", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-2555",
     "instructions_url": "https://www.irs.gov/instructions/i2555"},
    {"form_number": "1116", "sort_order": 101, "category": "individual", "subcategory": "credit", "title": "Foreign Tax Credit",
     "description": "Claims a credit for income taxes paid to foreign countries to reduce double taxation. Alternative to Form 2555 exclusion.",
     "who_files": "Taxpayer who paid foreign income taxes", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1116",
     "instructions_url": "https://www.irs.gov/instructions/i1116"},
    {"form_number": "FinCEN 114 (FBAR)", "sort_order": 102, "category": "individual", "subcategory": "disclosure", "title": "Report of Foreign Bank and Financial Accounts",
     "description": "Required for U.S. persons with foreign financial accounts totaling over $10,000 at any time during the year. Filed electronically with FinCEN by April 15.",
     "who_files": "Taxpayer with foreign accounts > $10,000", "filing_methods": ["efile"],
     "irs_url": "https://www.irs.gov/businesses/small-businesses-self-employed/report-of-foreign-bank-and-financial-accounts-fbar",
     "instructions_url": "https://www.irs.gov/businesses/small-businesses-self-employed/report-of-foreign-bank-and-financial-accounts-fbar"},
    {"form_number": "8938", "sort_order": 103, "category": "individual", "subcategory": "disclosure", "title": "Statement of Specified Foreign Financial Assets",
     "description": "Required under FATCA for taxpayers with foreign financial assets exceeding threshold ($50,000 for single filers). Filed with your 1040.",
     "who_files": "Taxpayer with substantial foreign assets", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-8938",
     "instructions_url": "https://www.irs.gov/instructions/i8938"},
    # Gambling / Crypto
    {"form_number": "W-2G", "sort_order": 110, "category": "informational", "subcategory": "income", "title": "Certain Gambling Winnings",
     "description": "Reports gambling winnings of $600+ (or $1,200+ from slots/bingo). Issued by casinos and gaming establishments.",
     "who_files": "Casino / gaming establishment", "provided_by": "Casino or gaming establishment",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-w-2-g",
     "instructions_url": "https://www.irs.gov/instructions/iw2g"},
    # Business Returns
    {"form_number": "1120", "sort_order": 200, "category": "business", "subcategory": "return", "title": "U.S. Corporation Income Tax Return",
     "description": "Annual tax return for C corporations.",
     "who_files": "C corporation", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1120",
     "instructions_url": "https://www.irs.gov/instructions/i1120"},
    {"form_number": "1120-S", "sort_order": 201, "category": "business", "subcategory": "return", "title": "U.S. Income Tax Return for an S Corporation",
     "description": "Annual return for S corporations. Income/loss passes through to shareholders' individual returns.",
     "who_files": "S corporation", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1120-s",
     "instructions_url": "https://www.irs.gov/instructions/i1120s"},
    {"form_number": "1065", "sort_order": 202, "category": "business", "subcategory": "return", "title": "U.S. Return of Partnership Income",
     "description": "Annual return for partnerships (including multi-member LLCs). Income/loss passes through to partners via Schedule K-1.",
     "who_files": "Partnership / multi-member LLC", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-1065",
     "instructions_url": "https://www.irs.gov/instructions/i1065"},
    {"form_number": "Schedule K-1 (1065)", "sort_order": 203, "category": "informational", "subcategory": "income", "title": "Partner's Share of Income, Deductions, Credits, etc.",
     "description": "Issued by the partnership to each partner showing their share of income, deductions, and credits.",
     "who_files": "Partnership", "provided_by": "Your partnership or LLC",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-k-1-form-1065",
     "instructions_url": "https://www.irs.gov/instructions/i1065sk1"},
    {"form_number": "Schedule K-1 (1120-S)", "sort_order": 204, "category": "informational", "subcategory": "income", "title": "Shareholder's Share of Income, Deductions, Credits, etc.",
     "description": "Issued by an S corporation to each shareholder showing their share of income, deductions, and credits.",
     "who_files": "S corporation", "provided_by": "Your S corporation",
     "filing_methods": [],
     "irs_url": "https://www.irs.gov/forms-pubs/about-schedule-k-1-form-1120-s",
     "instructions_url": "https://www.irs.gov/instructions/i1120ssk1"},
    {"form_number": "941", "sort_order": 210, "category": "employer", "subcategory": "employment", "title": "Employer's Quarterly Federal Tax Return",
     "description": "Quarterly return for employers to report federal income tax, Social Security, and Medicare taxes withheld from employees.",
     "who_files": "Employer", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-941",
     "instructions_url": "https://www.irs.gov/instructions/i941"},
    {"form_number": "940", "sort_order": 211, "category": "employer", "subcategory": "employment", "title": "Employer's Annual Federal Unemployment (FUTA) Tax Return",
     "description": "Annual return for employers to report and pay Federal Unemployment Tax Act (FUTA) tax.",
     "who_files": "Employer", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-940",
     "instructions_url": "https://www.irs.gov/instructions/i940"},
    # Military
    {"form_number": "3903", "sort_order": 300, "category": "individual", "subcategory": "deduction", "title": "Moving Expenses",
     "description": "Active-duty military members can deduct moving expenses related to a permanent change of station (PCS). Limited to military only since 2018.",
     "who_files": "Active-duty military member", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-3903",
     "instructions_url": "https://www.irs.gov/instructions/i3903"},
    # Miscellaneous
    {"form_number": "2210", "sort_order": 400, "category": "individual", "subcategory": "payment", "title": "Underpayment of Estimated Tax",
     "description": "Checks if you owe a penalty for underpaying estimated taxes during the year. Often waived if withholding covered 90%+ of liability.",
     "who_files": "Taxpayer who underpaid estimated taxes", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-2210",
     "instructions_url": "https://www.irs.gov/instructions/i2210"},
    {"form_number": "9465", "sort_order": 401, "category": "individual", "subcategory": "payment", "title": "Installment Agreement Request",
     "description": "Used to request a monthly installment plan if you cannot pay your full tax bill by the due date.",
     "who_files": "Taxpayer unable to pay in full", "filing_methods": ["mail", "efile"],
     "irs_url": "https://www.irs.gov/forms-pubs/about-form-9465",
     "instructions_url": "https://www.irs.gov/instructions/i9465"},
]


async def seed_federal_forms() -> None:
    async with get_db() as db:
        count = (await db.execute(select(FederalFormModel))).scalars().first()
        if count:
            return

        for f in FEDERAL_FORMS:
            db.add(FederalFormModel(
                form_number=f["form_number"],
                title=f["title"],
                description=f["description"],
                category=f["category"],
                subcategory=f.get("subcategory"),
                who_files=f["who_files"],
                provided_by=f.get("provided_by"),
                filing_methods=f.get("filing_methods", []),
                irs_url=f.get("irs_url"),
                instructions_url=f.get("instructions_url"),
                is_active=True,
                sort_order=f["sort_order"],
            ))
    print(f"[tax-seed] {len(FEDERAL_FORMS)} federal forms seeded.")


# ── 3. State Forms ────────────────────────────────────────────────────────────

STATE_FORMS = [
    {"state_code": "AL", "state_name": "Alabama", "form_number": "40", "title": "Individual Income Tax Return", "description": "Alabama individual income tax return for residents.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.revenue.alabama.gov/individual-corporate/individual-income-tax/", "has_income_tax": True},
    {"state_code": "AK", "state_name": "Alaska", "form_number": "N/A", "title": "No State Income Tax", "description": "Alaska has no state individual income tax. No state return required.", "category": "individual", "who_files": "N/A", "filing_methods": [], "state_web_url": "https://tax.alaska.gov", "has_income_tax": False},
    {"state_code": "AZ", "state_name": "Arizona", "form_number": "140", "title": "Resident Personal Income Tax Return", "description": "Arizona resident individual income tax return. Flat 2.5% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://azdor.gov/individual-income-tax-information", "has_income_tax": True},
    {"state_code": "AR", "state_name": "Arkansas", "form_number": "AR1000F", "title": "Full Year Resident Individual Income Tax Return", "description": "Arkansas full-year resident income tax return.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.dfa.arkansas.gov/income-tax/individual-income-tax/", "has_income_tax": True},
    {"state_code": "CA", "state_name": "California", "form_number": "540", "title": "California Resident Income Tax Return", "description": "California resident individual income tax return. Progressive rates up to 13.3%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.ftb.ca.gov/file/personal/", "has_income_tax": True},
    {"state_code": "CO", "state_name": "Colorado", "form_number": "DR 0104", "title": "Individual Income Tax Return", "description": "Colorado individual income tax return. Flat 4.40% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.colorado.gov/individual-income-tax", "has_income_tax": True},
    {"state_code": "CT", "state_name": "Connecticut", "form_number": "CT-1040", "title": "Connecticut Resident Income Tax Return", "description": "Connecticut resident income tax return with progressive rates 2%–6.99%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://portal.ct.gov/DRS/Individuals/Individual-Tax-Page", "has_income_tax": True},
    {"state_code": "DE", "state_name": "Delaware", "form_number": "200-01", "title": "Resident Individual Income Tax Return", "description": "Delaware resident income tax return with progressive rates up to 6.6%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://revenue.delaware.gov/individuals/personal-income-tax/", "has_income_tax": True},
    {"state_code": "FL", "state_name": "Florida", "form_number": "N/A", "title": "No State Income Tax", "description": "Florida has no state individual income tax. No state return required.", "category": "individual", "who_files": "N/A", "filing_methods": [], "state_web_url": "https://floridarevenue.com", "has_income_tax": False},
    {"state_code": "GA", "state_name": "Georgia", "form_number": "500", "title": "Individual Income Tax Return", "description": "Georgia individual income tax return. Flat 5.49% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://dor.georgia.gov/individual-income-tax", "has_income_tax": True},
    {"state_code": "HI", "state_name": "Hawaii", "form_number": "N-11", "title": "Hawaii Resident Income Tax Return", "description": "Hawaii resident income tax return with progressive rates up to 11%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.hawaii.gov/geninfo/whatisindtax/", "has_income_tax": True},
    {"state_code": "ID", "state_name": "Idaho", "form_number": "40", "title": "Idaho Individual Income Tax Return", "description": "Idaho resident income tax return. Flat 5.8% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.idaho.gov/taxes/income-tax/individual-income/", "has_income_tax": True},
    {"state_code": "IL", "state_name": "Illinois", "form_number": "IL-1040", "title": "Individual Income Tax Return", "description": "Illinois individual income tax return. Flat 4.95% rate.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.illinois.gov/individuals/individual-income-tax.html", "has_income_tax": True},
    {"state_code": "IN", "state_name": "Indiana", "form_number": "IT-40", "title": "Indiana Full-Year Resident Individual Income Tax Return", "description": "Indiana income tax return. Flat 3.15% state rate plus county taxes.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.in.gov/dor/individual-income-taxes/", "has_income_tax": True},
    {"state_code": "IA", "state_name": "Iowa", "form_number": "IA 1040", "title": "Iowa Individual Income Tax Return", "description": "Iowa income tax return. Moving to flat 3.8% rate by 2025.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.iowa.gov/individual-income-tax", "has_income_tax": True},
    {"state_code": "KS", "state_name": "Kansas", "form_number": "K-40", "title": "Kansas Individual Income Tax Return", "description": "Kansas income tax return with progressive rates 3.1%–5.7%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.ksrevenue.gov/persinc.html", "has_income_tax": True},
    {"state_code": "KY", "state_name": "Kentucky", "form_number": "740", "title": "Kentucky Individual Income Tax Return", "description": "Kentucky income tax return. Flat 4.0% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://revenue.ky.gov/Individual/Pages/default.aspx", "has_income_tax": True},
    {"state_code": "LA", "state_name": "Louisiana", "form_number": "IT-540", "title": "Louisiana Resident Individual Income Tax Return", "description": "Louisiana income tax return with progressive rates 1.85%–4.25%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://revenue.louisiana.gov/IndividualIncomeTax", "has_income_tax": True},
    {"state_code": "ME", "state_name": "Maine", "form_number": "1040ME", "title": "Maine Individual Income Tax Return", "description": "Maine income tax return with progressive rates 5.8%–7.15%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.maine.gov/revenue/taxes/income-estate-tax/individual-income-tax", "has_income_tax": True},
    {"state_code": "MD", "state_name": "Maryland", "form_number": "502", "title": "Maryland Resident Income Tax Return", "description": "Maryland income tax return with progressive rates 2%–5.75% plus local income tax.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.marylandtaxes.gov/individual/", "has_income_tax": True},
    {"state_code": "MA", "state_name": "Massachusetts", "form_number": "1", "title": "Massachusetts Resident Income Tax Return", "description": "Massachusetts income tax return. Flat 5% rate (plus 4% surtax on income over $1M).", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.mass.gov/orgs/massachusetts-department-of-revenue", "has_income_tax": True},
    {"state_code": "MI", "state_name": "Michigan", "form_number": "MI-1040", "title": "Michigan Individual Income Tax Return", "description": "Michigan income tax return. Flat 4.25% rate.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.michigan.gov/taxes/iit", "has_income_tax": True},
    {"state_code": "MN", "state_name": "Minnesota", "form_number": "M1", "title": "Minnesota Individual Income Tax Return", "description": "Minnesota income tax return with progressive rates 5.35%–9.85%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.revenue.state.mn.us/individual-income-tax", "has_income_tax": True},
    {"state_code": "MS", "state_name": "Mississippi", "form_number": "80-105", "title": "Mississippi Resident Individual Income Tax Return", "description": "Mississippi income tax return. Flat 4.7% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.dor.ms.gov/individual/ind-income-tax", "has_income_tax": True},
    {"state_code": "MO", "state_name": "Missouri", "form_number": "MO-1040", "title": "Missouri Individual Income Tax Long Form", "description": "Missouri income tax return with progressive rates up to 4.95%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://dor.mo.gov/individual/", "has_income_tax": True},
    {"state_code": "MT", "state_name": "Montana", "form_number": "2", "title": "Montana Individual Income Tax Return", "description": "Montana income tax return with progressive rates up to 6.75%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://mtrevenue.gov/taxes/individual-income-tax/", "has_income_tax": True},
    {"state_code": "NE", "state_name": "Nebraska", "form_number": "1040N", "title": "Nebraska Individual Income Tax Return", "description": "Nebraska income tax return with progressive rates.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://revenue.nebraska.gov/individuals", "has_income_tax": True},
    {"state_code": "NV", "state_name": "Nevada", "form_number": "N/A", "title": "No State Income Tax", "description": "Nevada has no state individual income tax. No state return required.", "category": "individual", "who_files": "N/A", "filing_methods": [], "state_web_url": "https://tax.nv.gov", "has_income_tax": False},
    {"state_code": "NH", "state_name": "New Hampshire", "form_number": "DP-10", "title": "Interest and Dividends Tax Return", "description": "New Hampshire taxes only interest and dividends at 3% for 2024 (eliminated January 1, 2025). No wage income tax.", "category": "individual", "who_files": "Taxpayer with interest/dividend income", "filing_methods": ["mail"], "state_web_url": "https://www.revenue.nh.gov/taxes/interest-dividends.htm", "has_income_tax": True},
    {"state_code": "NJ", "state_name": "New Jersey", "form_number": "NJ-1040", "title": "New Jersey Resident Income Tax Return", "description": "New Jersey income tax return with progressive rates 1.4%–10.75%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.nj.gov/treasury/taxation/njit35.shtml", "has_income_tax": True},
    {"state_code": "NM", "state_name": "New Mexico", "form_number": "PIT-1", "title": "New Mexico Personal Income Tax Return", "description": "New Mexico income tax return with progressive rates 1.7%–5.9%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.tax.newmexico.gov/individuals/", "has_income_tax": True},
    {"state_code": "NY", "state_name": "New York", "form_number": "IT-201", "title": "Resident Income Tax Return", "description": "New York resident income tax return with progressive rates 4%–10.9%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.tax.ny.gov/pit/file/it201_information.htm", "has_income_tax": True},
    {"state_code": "NC", "state_name": "North Carolina", "form_number": "D-400", "title": "Individual Income Tax Return", "description": "North Carolina income tax return. Flat 4.5% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.ncdor.gov/taxes-forms/individual-income-tax", "has_income_tax": True},
    {"state_code": "ND", "state_name": "North Dakota", "form_number": "ND-1", "title": "Individual Income Tax Return", "description": "North Dakota income tax return with progressive rates up to 2.5%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.nd.gov/tax/individual", "has_income_tax": True},
    {"state_code": "OH", "state_name": "Ohio", "form_number": "IT 1040", "title": "Ohio Individual Income Tax Return", "description": "Ohio income tax return with progressive rates 2.765%–3.99%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.ohio.gov/individual", "has_income_tax": True},
    {"state_code": "OK", "state_name": "Oklahoma", "form_number": "511", "title": "Oklahoma Resident Income Tax Return", "description": "Oklahoma income tax return with progressive rates 0.25%–4.75%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://oklahoma.gov/tax/individuals.html", "has_income_tax": True},
    {"state_code": "OR", "state_name": "Oregon", "form_number": "OR-40", "title": "Oregon Individual Income Tax Return (Resident)", "description": "Oregon income tax return with progressive rates 4.75%–9.9%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.oregon.gov/dor/programs/individuals/Pages/default.aspx", "has_income_tax": True},
    {"state_code": "PA", "state_name": "Pennsylvania", "form_number": "PA-40", "title": "Pennsylvania Personal Income Tax Return", "description": "Pennsylvania income tax return. Flat 3.07% rate.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.revenue.pa.gov/TaxesAndPrograms/PersonalIncomeTax/Pages/default.aspx", "has_income_tax": True},
    {"state_code": "RI", "state_name": "Rhode Island", "form_number": "RI-1040", "title": "Rhode Island Resident Individual Income Tax Return", "description": "Rhode Island income tax return with progressive rates 3.75%–5.99%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.ri.gov/tax-sections/income-taxes", "has_income_tax": True},
    {"state_code": "SC", "state_name": "South Carolina", "form_number": "SC1040", "title": "Individual Income Tax Return", "description": "South Carolina income tax return. Flat 6.4% rate for 2024.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://dor.sc.gov/tax/individual", "has_income_tax": True},
    {"state_code": "SD", "state_name": "South Dakota", "form_number": "N/A", "title": "No State Income Tax", "description": "South Dakota has no state individual income tax. No state return required.", "category": "individual", "who_files": "N/A", "filing_methods": [], "state_web_url": "https://dor.sd.gov", "has_income_tax": False},
    {"state_code": "TN", "state_name": "Tennessee", "form_number": "N/A", "title": "No State Income Tax", "description": "Tennessee eliminated its Hall Tax on interest and dividends in 2021. No state income tax required.", "category": "individual", "who_files": "N/A", "filing_methods": [], "state_web_url": "https://www.tn.gov/revenue", "has_income_tax": False},
    {"state_code": "TX", "state_name": "Texas", "form_number": "N/A", "title": "No State Income Tax", "description": "Texas has no state individual income tax. No state return required.", "category": "individual", "who_files": "N/A", "filing_methods": [], "state_web_url": "https://comptroller.texas.gov", "has_income_tax": False},
    {"state_code": "UT", "state_name": "Utah", "form_number": "TC-40", "title": "Utah Individual Income Tax Return", "description": "Utah income tax return. Flat 4.55% rate.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.utah.gov/individual", "has_income_tax": True},
    {"state_code": "VT", "state_name": "Vermont", "form_number": "IN-111", "title": "Vermont Income Tax Return", "description": "Vermont income tax return with progressive rates 3.35%–8.75%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.vermont.gov/individuals/income-tax", "has_income_tax": True},
    {"state_code": "VA", "state_name": "Virginia", "form_number": "760", "title": "Virginia Resident Individual Income Tax Return", "description": "Virginia income tax return with progressive rates 2%–5.75%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.tax.virginia.gov/individual-income-tax", "has_income_tax": True},
    {"state_code": "WA", "state_name": "Washington", "form_number": "N/A*", "title": "No General Income Tax (Capital Gains Tax Applies)", "description": "Washington has no general income tax. However, a 7% capital gains tax applies to gains over $262,000 for 2024.", "category": "individual", "who_files": "Taxpayer with capital gains >$262,000", "filing_methods": ["efile"], "state_web_url": "https://dor.wa.gov/taxes-rates/other-taxes/capital-gains-tax", "has_income_tax": False},
    {"state_code": "WV", "state_name": "West Virginia", "form_number": "IT-140", "title": "West Virginia Personal Income Tax Return", "description": "West Virginia income tax return with progressive rates.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://tax.wv.gov/Individuals/Pages/IndividualIncomeTax.aspx", "has_income_tax": True},
    {"state_code": "WI", "state_name": "Wisconsin", "form_number": "Form 1", "title": "Wisconsin Income Tax Return", "description": "Wisconsin income tax return with progressive rates 3.5%–7.65%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://www.revenue.wi.gov/pages/ise/individual.aspx", "has_income_tax": True},
    {"state_code": "WY", "state_name": "Wyoming", "form_number": "N/A", "title": "No State Income Tax", "description": "Wyoming has no state individual income tax. No state return required.", "category": "individual", "who_files": "N/A", "filing_methods": [], "state_web_url": "https://revenue.wyo.gov", "has_income_tax": False},
    {"state_code": "DC", "state_name": "District of Columbia", "form_number": "D-40", "title": "DC Individual Income Tax Return", "description": "DC resident income tax return with progressive rates 4%–10.75%.", "category": "individual", "who_files": "Taxpayer", "filing_methods": ["mail", "efile"], "state_web_url": "https://mytax.dc.gov/", "has_income_tax": True},
]


async def seed_state_forms() -> None:
    async with get_db() as db:
        count = (await db.execute(select(StateFormModel))).scalars().first()
        if count:
            return

        for f in STATE_FORMS:
            db.add(StateFormModel(
                state_code=f["state_code"],
                state_name=f["state_name"],
                form_number=f["form_number"],
                title=f["title"],
                description=f["description"],
                category=f["category"],
                who_files=f["who_files"],
                provided_by=None,
                filing_methods=f.get("filing_methods", []),
                state_web_url=f.get("state_web_url"),
                has_income_tax=f["has_income_tax"],
                is_active=True,
            ))
    print(f"[tax-seed] {len(STATE_FORMS)} state forms seeded.")


# ── 4. Tax Brackets ───────────────────────────────────────────────────────────

def _adj(n: float, tax_year: int) -> float:
    """Inflation-adjust a 2024 threshold to the target year (~3%/year)."""
    factor = math.pow(1.03, tax_year - 2024)
    return round(n * factor / 50) * 50


async def seed_tax_brackets(tax_year: int) -> None:
    async with get_db() as db:
        existing = (await db.execute(
            select(TaxBracketModel).where(TaxBracketModel.tax_year == tax_year)
        )).scalars().first()
        if existing:
            return

        a = lambda n: _adj(n, tax_year)

        brackets = [
            # Single
            (0.10, 0,         a(11600),  "single"),
            (0.12, a(11600),  a(47150),  "single"),
            (0.22, a(47150),  a(100525), "single"),
            (0.24, a(100525), a(191950), "single"),
            (0.32, a(191950), a(243725), "single"),
            (0.35, a(243725), a(609350), "single"),
            (0.37, a(609350), None,      "single"),
            # MFJ
            (0.10, 0,         a(23200),  "mfj"),
            (0.12, a(23200),  a(94300),  "mfj"),
            (0.22, a(94300),  a(201050), "mfj"),
            (0.24, a(201050), a(383900), "mfj"),
            (0.32, a(383900), a(487450), "mfj"),
            (0.35, a(487450), a(731200), "mfj"),
            (0.37, a(731200), None,      "mfj"),
            # MFS
            (0.10, 0,         a(11600),  "mfs"),
            (0.12, a(11600),  a(47150),  "mfs"),
            (0.22, a(47150),  a(100525), "mfs"),
            (0.24, a(100525), a(191950), "mfs"),
            (0.32, a(191950), a(243725), "mfs"),
            (0.35, a(243725), a(365600), "mfs"),
            (0.37, a(365600), None,      "mfs"),
            # HOH
            (0.10, 0,         a(16550),  "hoh"),
            (0.12, a(16550),  a(63100),  "hoh"),
            (0.22, a(63100),  a(100500), "hoh"),
            (0.24, a(100500), a(191950), "hoh"),
            (0.32, a(191950), a(243700), "hoh"),
            (0.35, a(243700), a(609350), "hoh"),
            (0.37, a(609350), None,      "hoh"),
            # QW (same as MFJ)
            (0.10, 0,         a(23200),  "qw"),
            (0.12, a(23200),  a(94300),  "qw"),
            (0.22, a(94300),  a(201050), "qw"),
            (0.24, a(201050), a(383900), "qw"),
            (0.32, a(383900), a(487450), "qw"),
            (0.35, a(487450), a(731200), "qw"),
            (0.37, a(731200), None,      "qw"),
        ]
        for rate, income_from, income_to, status in brackets:
            db.add(TaxBracketModel(
                tax_year=tax_year,
                filing_status=status,
                rate=rate,
                income_from=float(income_from),
                income_to=float(income_to) if income_to is not None else None,
            ))
    print(f"[tax-seed] {len(brackets)} tax brackets seeded for {tax_year}.")


# ── 5. Standard Deductions ────────────────────────────────────────────────────

async def seed_standard_deductions(tax_year: int) -> None:
    async with get_db() as db:
        existing = (await db.execute(
            select(StandardDeductionModel).where(StandardDeductionModel.tax_year == tax_year)
        )).scalars().first()
        if existing:
            return

        a = lambda n: _adj(n, tax_year)
        deductions = [
            ("single", a(14600), a(1950), a(1950)),
            ("mfj",    a(29200), a(1550), a(1550)),
            ("mfs",    a(14600), a(1550), a(1550)),
            ("hoh",    a(21900), a(1950), a(1950)),
            ("qw",     a(29200), a(1550), a(1550)),
        ]
        for status, base, add65, blind in deductions:
            db.add(StandardDeductionModel(
                tax_year=tax_year,
                filing_status=status,
                base_amount=float(base),
                age65_addition=float(add65),
                blind_addition=float(blind),
            ))
    print(f"[tax-seed] Standard deductions seeded for {tax_year}.")


# ── 6. Special Tax Rates ──────────────────────────────────────────────────────

async def seed_special_rates(tax_year: int) -> None:
    async with get_db() as db:
        existing = (await db.execute(
            select(SpecialTaxRateModel).where(SpecialTaxRateModel.tax_year == tax_year)
        )).scalars().first()
        if existing:
            return

        a = lambda n: _adj(n, tax_year)
        rates = [
            # FICA
            {"rate_type": "ss_employee",       "filing_status": None,     "rate": 0.062,  "wage_base": a(168600), "threshold_from": None,       "threshold_to": None,        "description": "Social Security tax (employee share). Applies to wages up to the wage base."},
            {"rate_type": "ss_employer",       "filing_status": None,     "rate": 0.062,  "wage_base": a(168600), "threshold_from": None,       "threshold_to": None,        "description": "Social Security tax (employer share). Matches employee contribution."},
            {"rate_type": "medicare_employee", "filing_status": None,     "rate": 0.0145, "wage_base": None,      "threshold_from": None,       "threshold_to": None,        "description": "Medicare tax (employee share). No wage base limit."},
            {"rate_type": "medicare_employer", "filing_status": None,     "rate": 0.0145, "wage_base": None,      "threshold_from": None,       "threshold_to": None,        "description": "Medicare tax (employer share). No wage base limit."},
            # Additional Medicare
            {"rate_type": "add_medicare_single","filing_status": "single", "rate": 0.009,  "wage_base": None,      "threshold_from": a(200000),  "threshold_to": None,        "description": "Additional 0.9% Medicare on wages over $200,000 (single/MFS)."},
            {"rate_type": "add_medicare_mfj",  "filing_status": "mfj",    "rate": 0.009,  "wage_base": None,      "threshold_from": a(250000),  "threshold_to": None,        "description": "Additional 0.9% Medicare on wages over $250,000 (MFJ)."},
            {"rate_type": "add_medicare_mfs",  "filing_status": "mfs",    "rate": 0.009,  "wage_base": None,      "threshold_from": a(125000),  "threshold_to": None,        "description": "Additional 0.9% Medicare on wages over $125,000 (MFS)."},
            # SE Tax
            {"rate_type": "se_full",           "filing_status": None,     "rate": 0.153,  "wage_base": a(168600), "threshold_from": None,       "threshold_to": None,        "description": "Self-employment tax (15.3%) on net SE earnings up to SS wage base."},
            {"rate_type": "se_med",            "filing_status": None,     "rate": 0.029,  "wage_base": None,      "threshold_from": a(168600),  "threshold_to": None,        "description": "Self-employment tax (2.9% Medicare portion) above SS wage base."},
            # NIIT
            {"rate_type": "niit_single",       "filing_status": "single", "rate": 0.038,  "wage_base": None,      "threshold_from": a(200000),  "threshold_to": None,        "description": "3.8% Net Investment Income Tax on investment income above threshold."},
            {"rate_type": "niit_mfj",          "filing_status": "mfj",    "rate": 0.038,  "wage_base": None,      "threshold_from": a(250000),  "threshold_to": None,        "description": "3.8% Net Investment Income Tax on investment income above threshold."},
            {"rate_type": "niit_mfs",          "filing_status": "mfs",    "rate": 0.038,  "wage_base": None,      "threshold_from": a(125000),  "threshold_to": None,        "description": "3.8% Net Investment Income Tax on investment income above threshold."},
            {"rate_type": "niit_hoh",          "filing_status": "hoh",    "rate": 0.038,  "wage_base": None,      "threshold_from": a(200000),  "threshold_to": None,        "description": "3.8% Net Investment Income Tax on investment income above threshold."},
            # Capital Gains
            {"rate_type": "ltcg_0_single",     "filing_status": "single", "rate": 0.00,   "wage_base": None,      "threshold_from": 0,          "threshold_to": a(47025),    "description": "0% long-term capital gains rate for single filers."},
            {"rate_type": "ltcg_15_single",    "filing_status": "single", "rate": 0.15,   "wage_base": None,      "threshold_from": a(47025),   "threshold_to": a(518900),   "description": "15% long-term capital gains rate for single filers."},
            {"rate_type": "ltcg_20_single",    "filing_status": "single", "rate": 0.20,   "wage_base": None,      "threshold_from": a(518900),  "threshold_to": None,        "description": "20% long-term capital gains rate for single filers."},
            {"rate_type": "ltcg_0_mfj",        "filing_status": "mfj",    "rate": 0.00,   "wage_base": None,      "threshold_from": 0,          "threshold_to": a(94050),    "description": "0% long-term capital gains rate for MFJ filers."},
            {"rate_type": "ltcg_15_mfj",       "filing_status": "mfj",    "rate": 0.15,   "wage_base": None,      "threshold_from": a(94050),   "threshold_to": a(583750),   "description": "15% long-term capital gains rate for MFJ filers."},
            {"rate_type": "ltcg_20_mfj",       "filing_status": "mfj",    "rate": 0.20,   "wage_base": None,      "threshold_from": a(583750),  "threshold_to": None,        "description": "20% long-term capital gains rate for MFJ filers."},
            # AMT
            {"rate_type": "amt_rate1",         "filing_status": None,     "rate": 0.26,   "wage_base": None,      "threshold_from": 0,          "threshold_to": a(232600),   "description": "26% AMT rate on AMTI up to threshold."},
            {"rate_type": "amt_rate2",         "filing_status": None,     "rate": 0.28,   "wage_base": None,      "threshold_from": a(232600),  "threshold_to": None,        "description": "28% AMT rate on AMTI above threshold."},
            {"rate_type": "amt_exempt_single", "filing_status": "single", "rate": 0.0,    "wage_base": None,      "threshold_from": a(85700),   "threshold_to": a(609350),   "description": "AMT exemption for single filers ($85,700, phases out at $609,350)."},
            {"rate_type": "amt_exempt_mfj",    "filing_status": "mfj",    "rate": 0.0,    "wage_base": None,      "threshold_from": a(133300),  "threshold_to": a(1218700),  "description": "AMT exemption for MFJ filers ($133,300, phases out at $1,218,700)."},
            # Kiddie Tax
            {"rate_type": "kiddie_unearned",   "filing_status": None,     "rate": 0.0,    "wage_base": None,      "threshold_from": a(2500),    "threshold_to": None,        "description": "Kiddie tax: unearned income over $2,500 taxed at parent's rate for children under 19."},
        ]
        for r in rates:
            db.add(SpecialTaxRateModel(
                tax_year=tax_year,
                rate_type=r["rate_type"],
                filing_status=r["filing_status"],
                rate=r["rate"],
                wage_base=float(r["wage_base"]) if r["wage_base"] is not None else None,
                threshold_from=float(r["threshold_from"]) if r["threshold_from"] is not None else None,
                threshold_to=float(r["threshold_to"]) if r["threshold_to"] is not None else None,
                description=r["description"],
            ))
    print(f"[tax-seed] {len(rates)} special tax rates seeded for {tax_year}.")


# ── 7. Questionnaire Questions ────────────────────────────────────────────────

QUESTIONS = [
    # Identity & Status
    {"question_key": "entity_type", "category": "identity", "sort_order": 1, "question_text": "Are you filing as an individual or a business?", "help_text": "Choose 'Individual' if you are filing a personal tax return (Form 1040). Choose 'Business' if you are filing for a corporation, partnership, or S-corp.", "input_type": "single_choice", "is_required": True, "applies_to_individual": True, "applies_to_business": True, "options": [{"value": "individual", "label": "Individual / Sole Proprietor"}, {"value": "business", "label": "Business (Corporation, Partnership, or S-Corp)"}]},
    {"question_key": "filing_status", "category": "identity", "sort_order": 2, "question_text": "What is your filing status for this tax year?", "help_text": "Your filing status affects your tax brackets, standard deduction, and eligibility for many credits.", "input_type": "single_choice", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False, "options": [{"value": "single", "label": "Single"}, {"value": "mfj", "label": "Married Filing Jointly"}, {"value": "mfs", "label": "Married Filing Separately"}, {"value": "hoh", "label": "Head of Household"}, {"value": "qw", "label": "Qualifying Surviving Spouse"}]},
    {"question_key": "age_65_or_older", "category": "identity", "sort_order": 3, "question_text": "Were you (or your spouse if filing jointly) age 65 or older as of December 31 of the tax year?", "help_text": "Taxpayers 65+ may use Form 1040-SR and receive a higher standard deduction.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "residency_status", "category": "identity", "sort_order": 4, "question_text": "What is your U.S. residency status?", "help_text": "This determines which tax return form applies to you.", "input_type": "single_choice", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False, "options": [{"value": "citizen_resident", "label": "U.S. Citizen or Resident Alien"}, {"value": "nonresident", "label": "Nonresident Alien"}, {"value": "dual_status", "label": "Dual-Status Alien"}]},
    {"question_key": "state_of_residence", "category": "identity", "sort_order": 5, "question_text": "What state did you live in for the majority of the tax year?", "help_text": "This determines which state income tax return(s) you may need to file.", "input_type": "state_select", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "military_status", "category": "identity", "sort_order": 6, "question_text": "What is your military status?", "help_text": "Active duty military members may qualify for special deductions and state tax exemptions.", "input_type": "single_choice", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False, "options": [{"value": "civilian", "label": "Civilian (not military)"}, {"value": "active_duty", "label": "Active Duty Military"}, {"value": "veteran", "label": "Veteran / Retired Military"}, {"value": "reserve", "label": "Reserve / National Guard"}]},
    {"question_key": "married_status_change", "category": "identity", "sort_order": 7, "question_text": "Did your marital status change during the tax year (married, divorced, or widowed)?", "help_text": "A change in marital status can affect your filing status, withholding, and applicable deductions.", "input_type": "yes_no", "is_required": False, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    # Income Sources
    {"question_key": "has_w2", "category": "income", "sort_order": 10, "question_text": "Did you receive a W-2 (wages from an employer) during the tax year?", "help_text": "W-2 income comes from being an employee. Your employer withholds income tax, Social Security, and Medicare. You should receive your W-2 by January 31.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_self_employment", "category": "income", "sort_order": 11, "question_text": "Did you earn income from self-employment, freelancing, or a side business?", "help_text": "This includes any work where you were paid as an independent contractor, received 1099-NEC forms, or ran your own business as a sole proprietor.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_rental_income", "category": "income", "sort_order": 12, "question_text": "Did you receive rental income from any property you own?", "help_text": "Rental income from houses, apartments, vacation rentals (Airbnb/VRBO), or commercial property must be reported.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_investment_income", "category": "income", "sort_order": 13, "question_text": "Did you have investment income (dividends, interest, or sold stocks/bonds/crypto)?", "help_text": "This includes stock dividends, mutual fund distributions, bank interest, capital gains from selling investments, or gains from cryptocurrency transactions.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_retirement_income", "category": "income", "sort_order": 14, "question_text": "Did you receive distributions from a pension, 401(k), IRA, or other retirement plan?", "help_text": "Any withdrawals from qualified retirement plans generate a 1099-R and may be taxable.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_social_security", "category": "income", "sort_order": 15, "question_text": "Did you receive Social Security benefits?", "help_text": "SSA-1099 is sent by the Social Security Administration. Up to 85% of benefits may be taxable depending on your combined income.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_unemployment", "category": "income", "sort_order": 16, "question_text": "Did you receive unemployment compensation?", "help_text": "Unemployment benefits are fully taxable and reported on Form 1099-G from your state.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_foreign_income", "category": "income", "sort_order": 17, "question_text": "Did you earn income in a foreign country or pay taxes to a foreign government?", "help_text": "Foreign income must be reported. You may qualify for the Foreign Earned Income Exclusion (Form 2555) or the Foreign Tax Credit (Form 1116).", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_gambling", "category": "income", "sort_order": 18, "question_text": "Did you have gambling winnings (casino, lottery, sports betting, online gaming)?", "help_text": "All gambling winnings are taxable. You may receive Form W-2G for larger winnings. You can deduct losses only if you itemize.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_partnership_k1", "category": "income", "sort_order": 19, "question_text": "Did you receive a Schedule K-1 from a partnership, S-corporation, trust, or estate?", "help_text": "K-1 forms report your share of income, deductions, and credits from pass-through entities.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    # Deductions & Adjustments
    {"question_key": "wants_itemize", "category": "deductions", "sort_order": 20, "question_text": "Do you think you may want to itemize your deductions instead of taking the standard deduction?", "help_text": "Itemizing makes sense if your deductible expenses (mortgage interest, state taxes, charity, medical) exceed the standard deduction ($14,600 single / $29,200 MFJ for 2024).", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_mortgage", "category": "deductions", "sort_order": 21, "question_text": "Did you pay mortgage interest on a home loan?", "help_text": "Your lender will send Form 1098 showing the mortgage interest paid. This is deductible if you itemize.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "sold_home", "category": "deductions", "sort_order": 22, "question_text": "Did you sell your primary home or any real estate during the tax year?", "help_text": "Gains on home sales may be excluded up to $250,000 ($500,000 MFJ). Any gain above the exclusion is taxable and reported on Schedule D.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_student_loan", "category": "deductions", "sort_order": 23, "question_text": "Did you pay student loan interest?", "help_text": "You can deduct up to $2,500 of student loan interest. Your servicer sends Form 1098-E if you paid $600 or more.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_hsa", "category": "deductions", "sort_order": 24, "question_text": "Did you contribute to or withdraw from a Health Savings Account (HSA)?", "help_text": "HSA contributions are tax-deductible. Withdrawals for qualified medical expenses are tax-free. Form 8889 is required.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    # Credits
    {"question_key": "has_dependents", "category": "credits", "sort_order": 30, "question_text": "Do you have qualifying children or dependents?", "help_text": "Qualifying children may entitle you to the Child Tax Credit ($2,000/child), Earned Income Credit, and other benefits.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_childcare_expenses", "category": "credits", "sort_order": 31, "question_text": "Did you pay for childcare or dependent care so you (and your spouse) could work or look for work?", "help_text": "Qualifying expenses for daycare, babysitters, or after-school programs for children under 13 may qualify for the Child and Dependent Care Credit.", "input_type": "yes_no", "is_required": True, "depends_on_key": "has_dependents", "depends_on_val": "yes", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_education_expenses", "category": "credits", "sort_order": 32, "question_text": "Did you (or a dependent) pay tuition for college, university, or a vocational school?", "help_text": "The American Opportunity Credit (up to $2,500) and Lifetime Learning Credit (up to $2,000) may apply. Your school sends Form 1098-T.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "adopted_child", "category": "credits", "sort_order": 33, "question_text": "Did you adopt a child during the tax year?", "help_text": "The Adoption Credit (up to $16,810 per child for 2024) is available for qualified adoption expenses.", "input_type": "yes_no", "is_required": False, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "made_retirement_contributions", "category": "credits", "sort_order": 34, "question_text": "Did you contribute to a traditional IRA, Roth IRA, or employer retirement plan (401k, 403b, etc.)?", "help_text": "Traditional IRA contributions may be deductible. All eligible contributions may qualify for the Saver's Credit if your income qualifies.", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    # Healthcare
    {"question_key": "health_insurance_source", "category": "healthcare", "sort_order": 40, "question_text": "What was your primary source of health insurance coverage during the tax year?", "help_text": "Your insurance source determines which tax forms are relevant to you.", "input_type": "single_choice", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False, "options": [{"value": "employer", "label": "Employer-provided insurance"}, {"value": "marketplace", "label": "Health Insurance Marketplace (Healthcare.gov / state exchange)"}, {"value": "medicare", "label": "Medicare"}, {"value": "medicaid", "label": "Medicaid / CHIP"}, {"value": "self_paid", "label": "Self-paid / Direct purchase"}, {"value": "military", "label": "TRICARE / VA coverage"}, {"value": "uninsured", "label": "I had no health insurance for part or all of the year"}, {"value": "multiple", "label": "Multiple sources"}]},
    # Special Situations
    {"question_key": "has_home_office", "category": "special", "sort_order": 50, "question_text": "Did you use part of your home exclusively and regularly for business purposes?", "help_text": "Self-employed individuals who use a dedicated space at home for their business may deduct home office expenses (Form 8829).", "input_type": "yes_no", "is_required": False, "depends_on_key": "has_self_employment", "depends_on_val": "yes", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_energy_improvements", "category": "special", "sort_order": 51, "question_text": "Did you make energy-efficiency improvements to your home (solar panels, heat pump, insulation, EV charger)?", "help_text": "The Residential Clean Energy Credit covers 30% of eligible costs for solar and battery systems.", "input_type": "yes_no", "is_required": False, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_noncash_donations", "category": "special", "sort_order": 52, "question_text": "Did you make noncash charitable donations totaling more than $500 (clothing, furniture, car, etc.)?", "help_text": "Noncash donations over $500 require Form 8283. Donations over $5,000 require a qualified appraisal.", "input_type": "yes_no", "is_required": False, "depends_on_key": "wants_itemize", "depends_on_val": "yes", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "early_retirement_withdrawal", "category": "special", "sort_order": 53, "question_text": "Did you take an early withdrawal (before age 59½) from a retirement account?", "help_text": "Early withdrawals generally incur a 10% penalty plus income taxes unless an exception applies.", "input_type": "yes_no", "is_required": False, "depends_on_key": "has_retirement_income", "depends_on_val": "yes", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "has_foreign_accounts", "category": "special", "sort_order": 54, "question_text": "Did you have any foreign bank or financial accounts with a total value over $10,000 at any point during the year?", "help_text": "If yes, you must file an FBAR (FinCEN Form 114) by April 15.", "input_type": "yes_no", "is_required": False, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "needs_extension", "category": "special", "sort_order": 55, "question_text": "Do you need more time to file and plan to request a filing extension?", "help_text": "An automatic 6-month extension (to October 15) is available by filing Form 4868.", "input_type": "yes_no", "is_required": False, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "made_estimated_payments", "category": "special", "sort_order": 56, "question_text": "Did you make quarterly estimated tax payments during the tax year?", "help_text": "If you made estimated payments (1040-ES), you'll report them on your return.", "input_type": "yes_no", "is_required": False, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    {"question_key": "owes_back_taxes", "category": "special", "sort_order": 57, "question_text": "Do you owe back taxes or expect to be unable to pay your full tax bill?", "help_text": "If you can't pay in full, you may set up an installment agreement with the IRS using Form 9465.", "input_type": "yes_no", "is_required": False, "depends_on_key": "entity_type", "depends_on_val": "individual", "applies_to_individual": True, "applies_to_business": False},
    # Business
    {"question_key": "business_entity_type", "category": "identity", "sort_order": 60, "question_text": "What type of business entity are you filing for?", "help_text": "The entity type determines which business return form to use.", "input_type": "single_choice", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "business", "applies_to_individual": False, "applies_to_business": True, "options": [{"value": "c_corp", "label": "C Corporation (Form 1120)"}, {"value": "s_corp", "label": "S Corporation (Form 1120-S)"}, {"value": "partnership", "label": "Partnership / Multi-Member LLC (Form 1065)"}, {"value": "sole_prop_llc", "label": "Single-Member LLC / Sole Proprietor (Schedule C on 1040)"}]},
    {"question_key": "has_employees", "category": "employer", "sort_order": 61, "question_text": "Do you have employees (W-2 employees, not contractors)?", "help_text": "Employers must file quarterly payroll tax returns (Form 941) and annual unemployment returns (Form 940).", "input_type": "yes_no", "is_required": True, "depends_on_key": "entity_type", "depends_on_val": "business", "applies_to_individual": False, "applies_to_business": True},
]


async def seed_questions() -> None:
    async with get_db() as db:
        count = (await db.execute(select(TaxQuestionModel))).scalars().first()
        if count:
            return

        for q in QUESTIONS:
            db.add(TaxQuestionModel(
                question_key=q["question_key"],
                category=q["category"],
                question_text=q["question_text"],
                help_text=q.get("help_text"),
                input_type=q["input_type"],
                options=q.get("options"),
                is_required=q.get("is_required", True),
                depends_on_key=q.get("depends_on_key"),
                depends_on_val=q.get("depends_on_val"),
                sort_order=q["sort_order"],
                applies_to_individual=q.get("applies_to_individual", True),
                applies_to_business=q.get("applies_to_business", False),
            ))
    print(f"[tax-seed] {len(QUESTIONS)} questionnaire questions seeded.")


# ── 8. Form Requirement Rules ─────────────────────────────────────────────────

FORM_RULES = [
    {"question_key": "entity_type",          "question_value": "individual",    "form_source": "federal", "form_number": "1040",                  "priority": "required", "note": "Every individual taxpayer files Form 1040."},
    {"question_key": "age_65_or_older",       "question_value": "yes",           "form_source": "federal", "form_number": "1040-SR",               "priority": "likely",   "note": "Taxpayers 65+ may use Form 1040-SR (larger print, same content as 1040)."},
    {"question_key": "residency_status",      "question_value": "nonresident",   "form_source": "federal", "form_number": "1040-NR",               "priority": "required", "note": "Nonresident aliens must file Form 1040-NR instead of Form 1040."},
    {"question_key": "has_w2",                "question_value": "yes",           "form_source": "federal", "form_number": "W-2",                   "priority": "required", "note": "Your employer provides Form W-2 by January 31. You'll need it to complete your 1040."},
    {"question_key": "has_self_employment",   "question_value": "yes",           "form_source": "federal", "form_number": "Schedule C",            "priority": "required", "note": "Schedule C reports profit or loss from your self-employed business."},
    {"question_key": "has_self_employment",   "question_value": "yes",           "form_source": "federal", "form_number": "Schedule SE",           "priority": "required", "note": "Schedule SE calculates your self-employment tax (Social Security + Medicare)."},
    {"question_key": "has_self_employment",   "question_value": "yes",           "form_source": "federal", "form_number": "1040-ES",               "priority": "likely",   "note": "If you expect to owe $1,000+ after withholding, you should make quarterly estimated tax payments."},
    {"question_key": "has_self_employment",   "question_value": "yes",           "form_source": "federal", "form_number": "8995",                  "priority": "likely",   "note": "You may qualify for the 20% Qualified Business Income deduction (Form 8995)."},
    {"question_key": "has_self_employment",   "question_value": "yes",           "form_source": "federal", "form_number": "1099-NEC",              "priority": "required", "note": "Clients who paid you $600+ will send you Form 1099-NEC."},
    {"question_key": "has_home_office",       "question_value": "yes",           "form_source": "federal", "form_number": "8829",                  "priority": "required", "note": "Form 8829 calculates your home office deduction."},
    {"question_key": "has_rental_income",     "question_value": "yes",           "form_source": "federal", "form_number": "Schedule E",            "priority": "required", "note": "Schedule E reports rental income and expenses."},
    {"question_key": "has_investment_income", "question_value": "yes",           "form_source": "federal", "form_number": "Schedule D",            "priority": "required", "note": "Schedule D summarizes capital gains and losses."},
    {"question_key": "has_investment_income", "question_value": "yes",           "form_source": "federal", "form_number": "8949",                  "priority": "required", "note": "Form 8949 details each capital asset sale (stocks, bonds, crypto, etc.)."},
    {"question_key": "has_investment_income", "question_value": "yes",           "form_source": "federal", "form_number": "1099-B",                "priority": "required", "note": "Your broker sends Form 1099-B showing proceeds from securities sales."},
    {"question_key": "has_investment_income", "question_value": "yes",           "form_source": "federal", "form_number": "1099-DIV",              "priority": "required", "note": "Your brokerage sends Form 1099-DIV for dividends of $10+."},
    {"question_key": "has_investment_income", "question_value": "yes",           "form_source": "federal", "form_number": "1099-INT",              "priority": "required", "note": "Banks send Form 1099-INT for interest income of $10+."},
    {"question_key": "has_investment_income", "question_value": "yes",           "form_source": "federal", "form_number": "Schedule B",            "priority": "likely",   "note": "Schedule B is required when interest/dividends exceed $1,500."},
    {"question_key": "has_retirement_income", "question_value": "yes",           "form_source": "federal", "form_number": "1099-R",                "priority": "required", "note": "Your plan administrator sends Form 1099-R for each distribution."},
    {"question_key": "early_retirement_withdrawal", "question_value": "yes",     "form_source": "federal", "form_number": "5329",                  "priority": "required", "note": "Form 5329 calculates the 10% early withdrawal penalty (unless an exception applies)."},
    {"question_key": "has_social_security",   "question_value": "yes",           "form_source": "federal", "form_number": "SSA-1099",              "priority": "required", "note": "The SSA sends you Form SSA-1099 showing your benefits. Up to 85% may be taxable."},
    {"question_key": "has_unemployment",      "question_value": "yes",           "form_source": "federal", "form_number": "1099-G",                "priority": "required", "note": "Your state sends Form 1099-G showing unemployment benefits paid."},
    {"question_key": "has_dependents",        "question_value": "yes",           "form_source": "federal", "form_number": "8812",                  "priority": "required", "note": "Form 8812 calculates the Child Tax Credit ($2,000/child) and Additional Child Tax Credit."},
    {"question_key": "has_childcare_expenses","question_value": "yes",           "form_source": "federal", "form_number": "2441",                  "priority": "required", "note": "Form 2441 claims the Child and Dependent Care Credit."},
    {"question_key": "has_education_expenses","question_value": "yes",           "form_source": "federal", "form_number": "8863",                  "priority": "required", "note": "Form 8863 claims the American Opportunity Credit or Lifetime Learning Credit."},
    {"question_key": "has_education_expenses","question_value": "yes",           "form_source": "federal", "form_number": "1098-T",                "priority": "required", "note": "Your school sends Form 1098-T showing tuition paid. Needed to complete Form 8863."},
    {"question_key": "adopted_child",         "question_value": "yes",           "form_source": "federal", "form_number": "8839",                  "priority": "required", "note": "Form 8839 claims the Adoption Credit (up to $16,810 per child for 2024)."},
    {"question_key": "made_retirement_contributions", "question_value": "yes",   "form_source": "federal", "form_number": "5498",                  "priority": "required", "note": "Your IRA custodian sends Form 5498 showing your contributions. Keep for your records."},
    {"question_key": "made_retirement_contributions", "question_value": "yes",   "form_source": "federal", "form_number": "8880",                  "priority": "likely",   "note": "Form 8880 claims the Saver's Credit for lower-income taxpayers contributing to retirement plans."},
    {"question_key": "has_mortgage",          "question_value": "yes",           "form_source": "federal", "form_number": "1098",                  "priority": "required", "note": "Your lender sends Form 1098 showing mortgage interest paid. Required to itemize."},
    {"question_key": "wants_itemize",         "question_value": "yes",           "form_source": "federal", "form_number": "Schedule A",            "priority": "required", "note": "Schedule A is used to itemize deductions (mortgage interest, SALT, charity, medical)."},
    {"question_key": "has_noncash_donations", "question_value": "yes",           "form_source": "federal", "form_number": "8283",                  "priority": "required", "note": "Form 8283 documents noncash charitable contributions over $500."},
    {"question_key": "has_student_loan",      "question_value": "yes",           "form_source": "federal", "form_number": "1098-E",                "priority": "required", "note": "Your loan servicer sends Form 1098-E for student loan interest of $600+."},
    {"question_key": "has_student_loan",      "question_value": "yes",           "form_source": "federal", "form_number": "Schedule 1",            "priority": "required", "note": "Schedule 1 is used to deduct student loan interest (up to $2,500)."},
    {"question_key": "has_hsa",               "question_value": "yes",           "form_source": "federal", "form_number": "8889",                  "priority": "required", "note": "Form 8889 reports HSA contributions and distributions."},
    {"question_key": "has_hsa",               "question_value": "yes",           "form_source": "federal", "form_number": "1099-SA",               "priority": "required", "note": "Your HSA administrator sends Form 1099-SA for distributions."},
    {"question_key": "has_hsa",               "question_value": "yes",           "form_source": "federal", "form_number": "5498-SA",               "priority": "required", "note": "Your HSA administrator sends Form 5498-SA showing contributions."},
    {"question_key": "health_insurance_source","question_value": "marketplace",  "form_source": "federal", "form_number": "1095-A",                "priority": "required", "note": "Healthcare.gov sends Form 1095-A showing Marketplace coverage. Required to complete Form 8962."},
    {"question_key": "health_insurance_source","question_value": "marketplace",  "form_source": "federal", "form_number": "8962",                  "priority": "required", "note": "Form 8962 reconciles advance premium tax credit payments with your actual eligibility."},
    {"question_key": "has_foreign_income",    "question_value": "yes",           "form_source": "federal", "form_number": "2555",                  "priority": "likely",   "note": "Form 2555 claims the Foreign Earned Income Exclusion (up to $126,500 for 2024) if you lived abroad."},
    {"question_key": "has_foreign_income",    "question_value": "yes",           "form_source": "federal", "form_number": "1116",                  "priority": "likely",   "note": "Form 1116 claims a credit for foreign income taxes paid, reducing double taxation."},
    {"question_key": "has_foreign_income",    "question_value": "yes",           "form_source": "federal", "form_number": "Schedule 3",            "priority": "required", "note": "Schedule 3 carries the Foreign Tax Credit from Form 1116 to your 1040."},
    {"question_key": "has_foreign_accounts",  "question_value": "yes",           "form_source": "federal", "form_number": "FinCEN 114 (FBAR)",     "priority": "required", "note": "FBAR must be filed electronically with FinCEN (not the IRS) by April 15."},
    {"question_key": "has_foreign_accounts",  "question_value": "yes",           "form_source": "federal", "form_number": "8938",                  "priority": "likely",   "note": "Form 8938 (FATCA) is required if foreign assets exceed $50,000 ($100,000 MFJ)."},
    {"question_key": "sold_home",             "question_value": "yes",           "form_source": "federal", "form_number": "8949",                  "priority": "required", "note": "Form 8949 reports the details of your home sale."},
    {"question_key": "sold_home",             "question_value": "yes",           "form_source": "federal", "form_number": "Schedule D",            "priority": "required", "note": "Schedule D summarizes the gain/loss from your home sale."},
    {"question_key": "has_energy_improvements","question_value": "yes",          "form_source": "federal", "form_number": "5695",                  "priority": "required", "note": "Form 5695 claims the Residential Clean Energy Credit (30% for solar) and Home Improvement Credit."},
    {"question_key": "has_gambling",          "question_value": "yes",           "form_source": "federal", "form_number": "W-2G",                  "priority": "required", "note": "Casinos send Form W-2G for winnings of $600+ (or $1,200+ for slots/bingo)."},
    {"question_key": "has_gambling",          "question_value": "yes",           "form_source": "federal", "form_number": "Schedule 1",            "priority": "required", "note": "Gambling winnings and losses are reported on Schedule 1."},
    {"question_key": "has_partnership_k1",    "question_value": "yes",           "form_source": "federal", "form_number": "Schedule K-1 (1065)",   "priority": "required", "note": "Your partnership or LLC provides Schedule K-1 showing your share of income/losses."},
    {"question_key": "needs_extension",       "question_value": "yes",           "form_source": "federal", "form_number": "4868",                  "priority": "required", "note": "File Form 4868 by April 15 for an automatic 6-month extension to file (not to pay)."},
    {"question_key": "made_estimated_payments","question_value": "yes",          "form_source": "federal", "form_number": "2210",                  "priority": "maybe",    "note": "Form 2210 checks if you owe an underpayment penalty."},
    {"question_key": "owes_back_taxes",       "question_value": "yes",           "form_source": "federal", "form_number": "9465",                  "priority": "likely",   "note": "Form 9465 requests a monthly installment plan if you can't pay your full tax bill."},
    {"question_key": "military_status",       "question_value": "active_duty",   "form_source": "federal", "form_number": "3903",                  "priority": "likely",   "note": "Active duty members can deduct PCS moving expenses on Form 3903."},
    {"question_key": "business_entity_type",  "question_value": "c_corp",        "form_source": "federal", "form_number": "1120",                  "priority": "required", "note": "C corporations file Form 1120."},
    {"question_key": "business_entity_type",  "question_value": "s_corp",        "form_source": "federal", "form_number": "1120-S",                "priority": "required", "note": "S corporations file Form 1120-S."},
    {"question_key": "business_entity_type",  "question_value": "partnership",   "form_source": "federal", "form_number": "1065",                  "priority": "required", "note": "Partnerships file Form 1065."},
    {"question_key": "business_entity_type",  "question_value": "partnership",   "form_source": "federal", "form_number": "Schedule K-1 (1065)",   "priority": "required", "note": "Form 1065 must include Schedule K-1 for each partner."},
    {"question_key": "business_entity_type",  "question_value": "sole_prop_llc", "form_source": "federal", "form_number": "Schedule C",            "priority": "required", "note": "Sole proprietors and single-member LLCs report on Schedule C attached to Form 1040."},
    {"question_key": "has_employees",         "question_value": "yes",           "form_source": "federal", "form_number": "941",                   "priority": "required", "note": "Employers file quarterly payroll tax returns on Form 941."},
    {"question_key": "has_employees",         "question_value": "yes",           "form_source": "federal", "form_number": "940",                   "priority": "required", "note": "Employers file an annual FUTA tax return on Form 940."},
    {"question_key": "has_employees",         "question_value": "yes",           "form_source": "federal", "form_number": "W-2",                   "priority": "required", "note": "Employers must issue W-2 to each employee by January 31."},
]


async def seed_form_rules() -> None:
    async with get_db() as db:
        count = (await db.execute(select(FormRequirementRuleModel))).scalars().first()
        if count:
            return

        for r in FORM_RULES:
            db.add(FormRequirementRuleModel(
                question_key=r["question_key"],
                question_value=r["question_value"],
                form_source=r["form_source"],
                form_number=r["form_number"],
                priority=r["priority"],
                note=r.get("note"),
            ))
    print(f"[tax-seed] {len(FORM_RULES)} form requirement rules seeded.")


# ── Master seed function ──────────────────────────────────────────────────────

async def seed_tax_data(tax_year: int) -> None:
    """Run all seed functions in order (idempotent)."""
    print(f"[tax-seed] Seeding tax data for {tax_year}...")
    await seed_tax_period(tax_year)
    await seed_federal_forms()
    await seed_state_forms()
    await seed_tax_brackets(tax_year)
    await seed_standard_deductions(tax_year)
    await seed_special_rates(tax_year)
    await seed_questions()
    await seed_form_rules()
    print(f"[tax-seed] ✓ All tax data seeded for {tax_year}.")
