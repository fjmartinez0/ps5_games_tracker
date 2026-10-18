"""Source readers. Each returns plain dicts and raises common.FetchError on network problems.

Parsers try several strategies (structured data first, page text last) because none of these sites
publish an official API. scripts/source_test.py saves raw samples so parsers can be fixed quickly
when a site changes its layout.
"""
