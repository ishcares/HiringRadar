import re

def _tag(t):
    t = t.lower()
    if re.search(r'\b(intern|internship|trainee|campus|fresher|new grad)\b', t): return 'Fresher/Intern'
    if re.search(r'\b(director|vp|vice president|head of|chief)\b', t): return 'Director/VP'
    if re.search(r'\b(engineering manager|tech lead|team lead|lead engineer)\b', t): return 'Manager/Lead'
    if re.search(r'\b(principal|staff|architect|sde-3|sde iii|sde3)\b', t): return 'Staff/Principal'
    if re.search(r'\b(senior|sr\.?)\b', t): return 'Senior'
    if re.search(r'\b(?:sde|swe|software\s+(?:development\s+)?engineer)(?:[\s-]*(?:ii|2))\b', t): return 'Mid-level'
    if re.search(r'\bengineer[\s-]*ii\b', t): return 'Mid-level'
    if re.search(r'\bengineer[\s-]*2\b', t): return 'Mid-level'
    if re.search(r'\b(junior|jr\.?|sde-1|sde1|associate)\b', t): return 'Junior'
    if re.search(r'\bengineer[\s-]*(?:i|1)\b', t): return 'Junior'
    return 'SoftwareEngineer'

BLOCKED = {'Senior', 'Mid-level', 'Director/VP', 'Manager/Lead', 'Staff/Principal'}

tests = [
    ('SDE-II, AI Core Infra - AI Analytics',          'Mid-level'),
    ('Software Development Engineer-II (SDE 2)',       'Mid-level'),
    ('SDE 2, FMA - Featured Merchant Algorithm',       'Mid-level'),
    ('Software Engineer, Translation Services',        'SoftwareEngineer'),
    ('Business Intelligence Engineer, Flex Analytics', 'SoftwareEngineer'),
    ('Software Engineer Intern',                       'Fresher/Intern'),
    ('Senior Software Engineer',                       'Senior'),
    ('Software Engineer',                              'SoftwareEngineer'),
    ('Software Development Engineer - I',              'Junior'),
    ('SWE-2, Payments Platform',                       'Mid-level'),
    ('Software Engineer II, Search',                   'Mid-level'),
    ('Engineer 2, Backend',                            'Mid-level'),
]

ok = True
for title, expected in tests:
    got = _tag(title)
    blocked = got in BLOCKED
    status = 'OK  ' if got == expected else 'FAIL'
    block_str = 'BLOCK' if blocked else 'ALLOW'
    print(f'  {status} [{block_str}] {got:<18} {title[:55]}')
    if got != expected:
        print(f'         Expected: {expected}')
        ok = False

print()
print('ALL PASS' if ok else 'FAILURES ABOVE -- check regex')
