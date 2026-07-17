from jd_skill_extractor import extract_skills_from_jd

jd_text = """Software Engineer
Apply
Cohesity
remote type
Hybrid
locations
Bangalore - India (Office)
time type
Full time
posted on
Posted 7 Days Ago
time left to apply
End Date: August 24, 2026 (30+ days left to apply)
job requisition id
R03374
Cohesity is the leader in AI-powered data security. Over 13,600 enterprise customers, including over 85 of the Fortune 100 and nearly 70% of the Global 500, rely on Cohesity to strengthen their resilience while providing Gen AI insights into their vast amounts of data. Formed from the combination of Cohesity with Veritas’ enterprise data protection business, the company’s solutions secure and protect data on-premises, in the cloud, and at the edge. Backed by NVIDIA, IBM, HPE, Cisco, AWS, Google Cloud, and others, Cohesity is headquartered in Santa Clara, CA, with offices around the globe.  

We’ve been named a Leader by multiple analyst firms and have been globally recognized for Innovation, Product Strength, and Simplicity in Design , and our culture. 

Want to join the leader in AI-powered data security? 

Cohesity offers a web-scale, hybrid cloud infrastructure for next-gen data management as a service. We are looking for Senior and Staff level Full Stack Software Engineers who are motivated and passionate about working on features, tools, and scripts that will improve the ability to sell, deploy and maintain Cohesity products. Our Software Engineers not only design and implement features but also diagnose problems in large bodies of sophisticated code, understand scalability and performance, and work on fixes with a rapid turnaround time and emphasis on high quality. We need experienced and outstanding engineers who strive to build high-quality distributed systems and solve complex problems.
This is an outstanding opportunity to join our Cohesity team in a period of fast growth and expansion. If you are interested in working in an environment where you can make an impact toward the future of cloud-based data management solutions, then Cohesity is the place for you.

HOW YOU'LL SPEND YOUR TIME HERE:

Own & develop designs for complete feature set
Engage in technical discussions with stakeholders -- Engineers, Architects, Product Managers and Designers
Fine tune backlog and adjust scope/plans to deliver committed features
Own deliverables by clearly communicating the scope, timelines and following through commitments
Continuously assess risks and make decisions based on metrics
Code and Implement features requested by Product Management and/or Customers for on-prem and cloud platforms
Perform in-depth root cause analysis, implement code fixes to resolve product defects
Deep dive into analyzing, troubleshooting and fixing functional and Performance issues
Collaborate with team members, support, QA and field teams to diagnose and troubleshoot complex customer issues and orchestrate development and testing of patches & hot-fixes
Design and implement tools to help support engineers diagnose problems thereby reducing time to resolution
This role requires an energetic, creative and driven individual with excellent communication and technical skills to partner with teams across the globe.

WE'D LOVE TO TALK TO YOU IF YOU HAVE MANY OF THE FOLLOWING:

2+ years of experience
Strong coding experience in any of these languages - C++, Python / Java / Go
Comfortable in using tools - JIRA, Github, Testrail
BS/MS in Computer Science or Engineering
Developing and troubleshooting large scale distributed systems written in C++,Python / Go / Java on Linux and Windows Platforms.
Strong coding, analytical, debugging and troubleshooting skills including use of tools such GDB, Python Debugger.
Problem-solver who can dive deep to solve complex problems/issues.
Bring good testing methodologies and passion for building quality products
Knowledge of Microservices and SaaS architecture
Looking for great communication skills.
Knowledge of agile/scrum methodologies
Exposure to Data Management domain is highly desirable
Ability to articulate design and implementation choices
Ability to make decisions based on data and influence stakeholders
Demonstrated ability to leverage AI tools to enhance productivity, streamline workflows, and support decision making.
#LI-AD1

Data Privacy Notice for Job Candidates:

For information on personal data processing, please see our Privacy Policy.


Equal Employment Opportunity Employer (EEOE)

Cohesity is an Equal Employment Opportunity Employer. All qualified applicants will receive consideration for employment without regard to race, color, creed, religion, sex, sexual orientation, national origin or nationality, ancestry, age, disability, gender identity or expression, marital status, veteran status or any other category protected by law.

If you are an individual with a disability and require a reasonable accommodation to complete any part of the application process, or are limited in the ability or unable to access or use this online application process and need an alternative method for applying, you may contact us at 1-855-9COHESITY or recruiting@cohesity.com for assistance.

In-Office Expectations

Cohesity employees who are within a reasonable commute (e.g. within a forty-five (45) minute average travel time) work out of our core offices 2-3 days a week of their choosing.

"""

from jd_skill_extractor import extract_skills_from_jd

result = extract_skills_from_jd("Software Engineer", "Cohesity", jd_text)
print(result)