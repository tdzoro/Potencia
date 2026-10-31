"""Skill taxonomy: canonical names, aliases and categories.

Two problems this module solves, both of which change scores downstream:

1. **Normalisation.** "JS", "JavaScript" and "javascript" are one skill. Without
   canonical names, a resume looks like it has more skills than it does, and
   matching against a job description fails on spelling.
2. **Context.** A few aliases are ordinary English words ("go", "rust", "swift",
   "spring", "ray"). Matching those in running prose produces false skills, so
   they are marked ambiguous and only matched inside an explicit skills list —
   see `find_skills(..., include_ambiguous=True)`.

Detection is deliberately conservative: a missed skill costs a little recall,
while a fabricated one tells a user they have experience they do not have.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (canonical, category, aliases)
_RAW: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # --- Languages ---
    ("Python", "language", ("python", "python3", "py")),
    ("JavaScript", "language", ("javascript", "js", "ecmascript", "es6")),
    ("TypeScript", "language", ("typescript", "ts")),
    ("Java", "language", ("java",)),
    ("C", "language", ("c",)),
    ("C++", "language", ("c++", "cpp")),
    ("C#", "language", ("c#", "csharp", "c sharp")),
    ("Go", "language", ("go", "golang")),
    ("Rust", "language", ("rust",)),
    ("Ruby", "language", ("ruby",)),
    ("PHP", "language", ("php",)),
    ("R", "language", ("r",)),
    ("Swift", "language", ("swift",)),
    ("Kotlin", "language", ("kotlin",)),
    ("Scala", "language", ("scala",)),
    ("MATLAB", "language", ("matlab",)),
    ("Perl", "language", ("perl",)),
    ("Elixir", "language", ("elixir",)),
    ("Haskell", "language", ("haskell",)),
    ("Lua", "language", ("lua",)),
    ("Dart", "language", ("dart",)),
    ("SQL", "language", ("sql",)),
    ("Bash", "language", ("bash", "shell scripting", "shell script")),
    ("PowerShell", "language", ("powershell",)),
    ("HTML", "language", ("html", "html5")),
    ("CSS", "language", ("css", "css3")),
    ("Sass", "language", ("sass", "scss")),
    ("Solidity", "language", ("solidity",)),
    ("Objective-C", "language", ("objective-c", "objc")),
    ("Fortran", "language", ("fortran",)),
    ("Julia", "language", ("julia",)),
    ("Groovy", "language", ("groovy",)),
    ("Clojure", "language", ("clojure",)),
    ("F#", "language", ("f#",)),
    ("Erlang", "language", ("erlang",)),
    ("OCaml", "language", ("ocaml",)),
    ("VBA", "language", ("vba",)),
    ("Visual Basic", "language", ("visual basic", "vb.net")),
    ("Assembly", "language", ("assembly", "x86 assembly")),
    ("GraphQL", "language", ("graphql",)),
    # --- Frontend ---
    ("React", "frontend", ("react", "react.js", "reactjs")),
    ("Vue.js", "frontend", ("vue", "vue.js", "vuejs")),
    ("Angular", "frontend", ("angular", "angularjs")),
    ("Svelte", "frontend", ("svelte", "sveltekit")),
    ("Next.js", "frontend", ("next.js", "nextjs")),
    ("Nuxt.js", "frontend", ("nuxt", "nuxt.js", "nuxtjs")),
    ("Redux", "frontend", ("redux", "redux toolkit")),
    ("Tailwind CSS", "frontend", ("tailwind", "tailwind css", "tailwindcss")),
    ("Bootstrap", "frontend", ("bootstrap",)),
    ("Material UI", "frontend", ("material ui", "mui", "material-ui")),
    ("jQuery", "frontend", ("jquery",)),
    ("Three.js", "frontend", ("three.js", "threejs")),
    ("D3.js", "frontend", ("d3", "d3.js")),
    ("Chart.js", "frontend", ("chart.js", "chartjs")),
    ("WebGL", "frontend", ("webgl",)),
    ("Accessibility", "frontend", ("accessibility", "a11y", "wcag")),
    # --- Backend ---
    ("Node.js", "backend", ("node", "node.js", "nodejs")),
    ("Express.js", "backend", ("express", "express.js", "expressjs")),
    ("Django", "backend", ("django",)),
    ("Flask", "backend", ("flask",)),
    ("FastAPI", "backend", ("fastapi",)),
    ("Spring Boot", "backend", ("spring boot", "springboot")),
    ("Spring", "backend", ("spring", "spring framework")),
    ("Laravel", "backend", ("laravel",)),
    ("Ruby on Rails", "backend", ("ruby on rails", "rails")),
    (".NET", "backend", (".net", "dotnet")),
    ("ASP.NET Core", "backend", ("asp.net", "asp.net core", "aspnet")),
    ("NestJS", "backend", ("nestjs", "nest.js")),
    ("Hibernate", "backend", ("hibernate",)),
    ("REST APIs", "backend", ("rest", "rest api", "rest apis", "restful")),
    ("gRPC", "backend", ("grpc",)),
    ("WebSockets", "backend", ("websocket", "websockets")),
    ("Celery", "backend", ("celery",)),
    ("Microservices", "backend", ("microservices", "microservice architecture")),
    ("Serverless", "backend", ("serverless",)),
    ("OAuth", "backend", ("oauth", "oauth2", "openid connect")),
    ("JWT", "backend", ("jwt", "json web token")),
    # --- Mobile / desktop ---
    ("React Native", "mobile", ("react native",)),
    ("Flutter", "mobile", ("flutter",)),
    ("Android", "mobile", ("android", "android sdk")),
    ("iOS", "mobile", ("ios", "ios sdk")),
    ("Xamarin", "mobile", ("xamarin",)),
    ("Ionic", "mobile", ("ionic",)),
    ("Electron", "desktop", ("electron",)),
    ("Unity", "desktop", ("unity", "unity3d")),
    ("Unreal Engine", "desktop", ("unreal", "unreal engine")),
    # --- Databases ---
    ("PostgreSQL", "database", ("postgres", "postgresql", "psql")),
    ("MySQL", "database", ("mysql",)),
    ("SQLite", "database", ("sqlite",)),
    ("MongoDB", "database", ("mongodb", "mongo")),
    ("Redis", "database", ("redis",)),
    ("Cassandra", "database", ("cassandra",)),
    ("DynamoDB", "database", ("dynamodb",)),
    ("Elasticsearch", "database", ("elasticsearch", "elastic search")),
    ("Oracle Database", "database", ("oracle db", "oracle database", "oracle")),
    ("SQL Server", "database", ("sql server", "mssql", "t-sql")),
    ("MariaDB", "database", ("mariadb",)),
    ("Neo4j", "database", ("neo4j",)),
    ("Snowflake", "database", ("snowflake",)),
    ("BigQuery", "database", ("bigquery", "big query")),
    ("Redshift", "database", ("redshift",)),
    ("ClickHouse", "database", ("clickhouse",)),
    ("HBase", "database", ("hbase",)),
    ("CouchDB", "database", ("couchdb",)),
    ("Firestore", "database", ("firestore", "firebase")),
    # --- Cloud / platform ---
    ("AWS", "cloud", ("aws", "amazon web services")),
    ("Azure", "cloud", ("azure", "microsoft azure")),
    ("Google Cloud Platform", "cloud", ("gcp", "google cloud", "google cloud platform")),
    ("Lambda", "cloud", ("aws lambda", "lambda functions")),
    ("EC2", "cloud", ("ec2",)),
    ("S3", "cloud", ("s3", "aws s3")),
    ("CloudFront", "cloud", ("cloudfront",)),
    ("Vercel", "cloud", ("vercel",)),
    ("Netlify", "cloud", ("netlify",)),
    ("Heroku", "cloud", ("heroku",)),
    ("Cloudflare", "cloud", ("cloudflare",)),
    ("OpenShift", "cloud", ("openshift",)),
    ("Firebase", "cloud", ("firebase",)),
    # --- DevOps ---
    ("Docker", "devops", ("docker", "dockerfile", "docker compose")),
    ("Kubernetes", "devops", ("kubernetes", "k8s")),
    ("Terraform", "devops", ("terraform",)),
    ("Ansible", "devops", ("ansible",)),
    ("Jenkins", "devops", ("jenkins",)),
    ("GitHub Actions", "devops", ("github actions",)),
    ("GitLab CI", "devops", ("gitlab ci", "gitlab ci/cd")),
    ("CircleCI", "devops", ("circleci",)),
    ("ArgoCD", "devops", ("argocd", "argo cd")),
    ("Helm", "devops", ("helm",)),
    ("Prometheus", "devops", ("prometheus",)),
    ("Grafana", "devops", ("grafana",)),
    ("Datadog", "devops", ("datadog",)),
    ("Nginx", "devops", ("nginx",)),
    ("Apache Kafka", "devops", ("kafka", "apache kafka")),
    ("RabbitMQ", "devops", ("rabbitmq",)),
    ("SQS", "devops", ("sqs", "amazon sqs")),
    ("Istio", "devops", ("istio",)),
    ("CI/CD", "devops", ("ci/cd", "cicd", "continuous integration", "continuous delivery")),
    ("Linux", "devops", ("linux", "ubuntu", "debian", "centos")),
    ("Unix", "devops", ("unix",)),
    ("Git", "tool", ("git",)),
    ("GitHub", "tool", ("github",)),
    ("GitLab", "tool", ("gitlab",)),
    ("Bitbucket", "tool", ("bitbucket",)),
    ("Jira", "tool", ("jira",)),
    ("Confluence", "tool", ("confluence",)),
    ("Notion", "tool", ("notion",)),
    ("Asana", "tool", ("asana",)),
    ("Trello", "tool", ("trello",)),
    ("Sentry", "tool", ("sentry",)),
    ("ELK Stack", "devops", ("elk", "elk stack", "kibana", "logstash")),
    ("Vault", "devops", ("hashicorp vault",)),
    # --- Testing ---
    ("Pytest", "testing", ("pytest", "py.test")),
    ("JUnit", "testing", ("junit",)),
    ("Selenium", "testing", ("selenium",)),
    ("Cypress", "testing", ("cypress",)),
    ("Playwright", "testing", ("playwright",)),
    ("Jest", "testing", ("jest",)),
    ("Mocha", "testing", ("mocha",)),
    ("Vitest", "testing", ("vitest",)),
    ("Storybook", "testing", ("storybook",)),
    ("Postman", "testing", ("postman",)),
    ("Test Automation", "testing", ("test automation", "automated testing")),
    ("Unit Testing", "testing", ("unit testing", "unit tests")),
    # --- Data / ML ---
    ("Pandas", "data", ("pandas",)),
    ("NumPy", "data", ("numpy",)),
    ("SciPy", "data", ("scipy",)),
    ("Scikit-learn", "data", ("scikit-learn", "sklearn", "scikit learn")),
    ("TensorFlow", "data", ("tensorflow",)),
    ("PyTorch", "data", ("pytorch", "torch")),
    ("Keras", "data", ("keras",)),
    ("XGBoost", "data", ("xgboost",)),
    ("LightGBM", "data", ("lightgbm",)),
    ("CatBoost", "data", ("catboost",)),
    ("OpenCV", "data", ("opencv",)),
    ("NLTK", "data", ("nltk",)),
    ("spaCy", "data", ("spacy",)),
    ("Hugging Face Transformers", "data", ("hugging face", "transformers", "huggingface")),
    ("LangChain", "data", ("langchain",)),
    ("Apache Spark", "data", ("spark", "apache spark", "pyspark")),
    ("Hadoop", "data", ("hadoop",)),
    ("Airflow", "data", ("airflow", "apache airflow")),
    ("dbt", "data", ("dbt",)),
    ("MLflow", "data", ("mlflow",)),
    ("Kubeflow", "data", ("kubeflow",)),
    ("Dask", "data", ("dask",)),
    ("Polars", "data", ("polars",)),
    ("Statsmodels", "data", ("statsmodels",)),
    ("Matplotlib", "data", ("matplotlib",)),
    ("Seaborn", "data", ("seaborn",)),
    ("Jupyter", "data", ("jupyter", "jupyter notebook", "notebooks")),
    ("Tableau", "data", ("tableau",)),
    ("Power BI", "data", ("power bi", "powerbi")),
    ("Looker", "data", ("looker",)),
    ("ETL", "data", ("etl", "extract transform load")),
    ("Data Warehousing", "data", ("data warehouse", "data warehousing")),
    ("Data Modeling", "data", ("data modeling", "data modelling")),
    ("Feature Engineering", "data", ("feature engineering",)),
    ("A/B Testing", "data", ("a/b testing", "ab testing", "split testing")),
    ("Statistics", "data", ("statistics", "statistical analysis", "statistical modeling")),
    ("Machine Learning", "data", ("machine learning", "ml models")),
    ("Deep Learning", "data", ("deep learning", "neural networks")),
    ("Natural Language Processing", "data", ("nlp", "natural language processing")),
    ("Computer Vision", "data", ("computer vision",)),
    ("Reinforcement Learning", "data", ("reinforcement learning",)),
    ("LLMs", "data", ("llm", "llms", "large language models")),
    ("RAG", "data", ("rag", "retrieval augmented generation")),
    ("Prompt Engineering", "data", ("prompt engineering",)),
    ("MLOps", "data", ("mlops",)),
    # --- Design ---
    ("Figma", "design", ("figma",)),
    ("Sketch", "design", ("sketch",)),
    ("Adobe XD", "design", ("adobe xd",)),
    ("Photoshop", "design", ("photoshop",)),
    ("Illustrator", "design", ("illustrator",)),
    ("After Effects", "design", ("after effects",)),
    ("Premiere Pro", "design", ("premiere pro", "premiere")),
    ("Blender", "design", ("blender",)),
    ("Canva", "design", ("canva",)),
    ("UI/UX Design", "design", ("ui/ux", "ux design", "ui design", "user experience")),
    # --- Product / project ---
    ("Project Management", "product", ("project management",)),
    ("Agile", "product", ("agile", "agile methodologies")),
    ("Scrum", "product", ("scrum",)),
    ("Kanban", "product", ("kanban",)),
    ("Product Management", "product", ("product management", "product roadmap")),
    ("Stakeholder Management", "product", ("stakeholder management", "stakeholders")),
    ("Roadmapping", "product", ("roadmap", "roadmapping")),
    ("Requirements Gathering", "product", ("requirements gathering", "requirement analysis")),
    ("Technical Writing", "product", ("technical writing", "documentation")),
    ("Six Sigma", "product", ("six sigma",)),
    ("Lean", "product", ("lean manufacturing", "lean methodology")),
    ("Process Improvement", "product", ("process improvement", "process optimization")),
    ("Quality Assurance", "product", ("quality assurance", "qa")),
    # --- Business / marketing / finance ---
    ("Salesforce", "business", ("salesforce",)),
    ("HubSpot", "business", ("hubspot",)),
    ("SAP", "business", ("sap",)),
    ("CRM", "business", ("crm", "customer relationship management")),
    ("SEO", "marketing", ("seo", "search engine optimization")),
    ("SEM", "marketing", ("sem", "search engine marketing", "google ads")),
    ("Google Analytics", "marketing", ("google analytics", "ga4")),
    ("Content Marketing", "marketing", ("content marketing",)),
    ("Copywriting", "marketing", ("copywriting",)),
    ("Social Media Marketing", "marketing", ("social media marketing", "social media")),
    ("Email Marketing", "marketing", ("email marketing",)),
    ("Market Research", "marketing", ("market research",)),
    ("Financial Modeling", "finance", ("financial modeling", "financial modelling")),
    ("Financial Analysis", "finance", ("financial analysis",)),
    ("Budgeting", "finance", ("budgeting", "budget management")),
    ("Forecasting", "finance", ("forecasting",)),
    ("Risk Management", "finance", ("risk management",)),
    ("Compliance", "finance", ("compliance",)),
    ("Auditing", "finance", ("auditing", "internal audit")),
    ("Accounting", "finance", ("accounting", "bookkeeping")),
    ("Excel", "business", ("excel", "microsoft excel", "spreadsheets")),
    ("PowerPoint", "business", ("powerpoint", "power point")),
    ("Business Development", "business", ("business development",)),
    ("Account Management", "business", ("account management",)),
    ("Sales", "business", ("sales", "b2b sales")),
    ("Negotiation", "business", ("negotiation",)),
    ("Supply Chain", "business", ("supply chain",)),
    ("Logistics", "business", ("logistics",)),
    ("Procurement", "business", ("procurement",)),
    ("Inventory Management", "business", ("inventory management",)),
    ("Customer Service", "business", ("customer service", "customer support")),
    ("Recruiting", "people", ("recruiting", "talent acquisition")),
    ("Onboarding", "people", ("onboarding",)),
    ("People Management", "people", ("people management", "team management")),
    ("Leadership", "people", ("leadership",)),
    ("Mentoring", "people", ("mentoring", "mentorship")),
    ("Public Speaking", "people", ("public speaking",)),
    ("Presentation Skills", "people", ("presentation skills", "presentations")),
    ("Communication", "people", ("communication skills",)),
    ("Research", "people", ("research", "qualitative research", "quantitative research")),
)

# Ordinary English words that are also skill names. Matching these in prose
# fabricates skills, so they only count inside an explicit skills list.
AMBIGUOUS_ALIASES: frozenset[str] = frozenset(
    {"go", "c", "r", "rust", "swift", "spring", "ray", "vault", "looker", "lean", "sales"}
)

_CATEGORY_BY_CANONICAL: dict[str, str] = {}
_ALIAS_INDEX: dict[str, str] = {}

for _canonical, _category, _aliases in _RAW:
    _CATEGORY_BY_CANONICAL[_canonical] = _category
    _ALIAS_INDEX[_canonical.lower()] = _canonical
    for _alias in _aliases:
        _ALIAS_INDEX.setdefault(_alias.lower(), _canonical)


def _normalise_key(name: str) -> str:
    """Fold case, punctuation runs and whitespace so lookups are forgiving."""
    key = name.strip().lower()
    key = re.sub(r"\s+", " ", key)
    key = key.strip(" .,;:•-–—|/()[]{}")
    return key


def canonicalise(name: str) -> str | None:
    """Return the canonical skill name, or `None` when it is not a known skill.

    Returning `None` rather than echoing the input is deliberate: callers must
    decide whether an unknown token is a real skill they should preserve, not
    have it silently promoted to a canonical one.
    """
    if not name:
        return None
    return _ALIAS_INDEX.get(_normalise_key(name))


def category_of(name: str) -> str | None:
    canonical = canonicalise(name)
    if canonical is None:
        return None
    return _CATEGORY_BY_CANONICAL.get(canonical)


def _build_pattern() -> re.Pattern[str]:
    # Longest alias first so "React Native" wins over "React" and "Node.js"
    # wins over "Node".
    aliases = sorted(_ALIAS_INDEX, key=len, reverse=True)
    alternation = "|".join(re.escape(alias) for alias in aliases)
    return re.compile(
        rf"(?<![A-Za-z0-9])(?:{alternation})(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


_PATTERN = _build_pattern()


def find_skills(text: str, *, include_ambiguous: bool = False) -> list[str]:
    """Return canonical skills found in `text`, ordered by first appearance.

    `include_ambiguous=True` is only appropriate for an explicit skills list,
    where "Go" or "Rust" cannot plausibly be a verb or a metal.
    """
    if not text:
        return []

    found: list[str] = []
    seen: set[str] = set()

    for match in _PATTERN.finditer(text):
        matched_text = match.group(0)
        if not include_ambiguous and _normalise_key(matched_text) in AMBIGUOUS_ALIASES:
            continue
        canonical = _ALIAS_INDEX.get(_normalise_key(matched_text))
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        found.append(canonical)

    return found


def all_canonical_names() -> list[str]:
    return sorted(_CATEGORY_BY_CANONICAL)


def size() -> int:
    """Number of canonical skills. Used by tests to assert real coverage."""
    return len(_CATEGORY_BY_CANONICAL)


@dataclass(frozen=True)
class SkillMatch:
    canonical: str
    category: str
    start: int

    @property
    def end(self) -> int:
        return self.start + len(self.canonical)


def match_skills_with_spans(text: str, *, include_ambiguous: bool = False) -> list[SkillMatch]:
    """Like `find_skills`, but keeps the character offset of each match.

    Job matching needs the surrounding window to tell a genuine requirement from
    a keyword that merely appears in the description.
    """
    if not text:
        return []

    matches: list[SkillMatch] = []
    seen: set[str] = set()

    for match in _PATTERN.finditer(text):
        matched_text = match.group(0)
        if not include_ambiguous and _normalise_key(matched_text) in AMBIGUOUS_ALIASES:
            continue
        canonical = _ALIAS_INDEX.get(_normalise_key(matched_text))
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        matches.append(
            SkillMatch(
                canonical=canonical,
                category=_CATEGORY_BY_CANONICAL.get(canonical, "other"),
                start=match.start(),
            )
        )

    return matches
