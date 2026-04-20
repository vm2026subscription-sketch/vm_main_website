import io
import os
import re
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

try:
    import pandas as pd
except ImportError:
    pd = None

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from dotenv import load_dotenv
try:
    from psycopg2 import connect
    from psycopg2.extras import Json, execute_values
except ImportError:
    connect = None
    Json = None
    execute_values = None

from supabase import create_client

load_dotenv()

app = Flask(__name__)
app.secret_key = "vidyarthi-mitra-dev-key"
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024  # 15 MB upload limit

COURSES_DB_URL = (
    os.getenv("SUPABASE_POSTGRES_URL", "").strip()
    or os.getenv("DATABASE_URL", "").strip()
)
if COURSES_DB_URL:
    try:
        from courses_routes import courses_bp

        app.register_blueprint(courses_bp)
    except Exception as exc:
        app.logger.warning("Skipping courses blueprint registration: %s", exc)

VMADMIN_BASE_URL = (
    os.getenv("VMADMIN_BASE_URL", "").strip().rstrip("/")
)


def fetch_remote_json(url, timeout=12):
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "vm-main-website/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            if not body:
                return []
            return json.loads(body.decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError, UnicodeDecodeError):
        return None


def extract_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("results", "items", "news", "editions", "articles"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    data_value = payload.get("data")
    if isinstance(data_value, list):
        return data_value

    if isinstance(data_value, dict):
        for key in ("results", "items", "news", "editions", "articles"):
            value = data_value.get(key)
            if isinstance(value, list):
                return value

    return []


def extract_next_url(payload, current_url):
    if not isinstance(payload, dict):
        return None

    candidate = payload.get("next")
    if not candidate and isinstance(payload.get("pagination"), dict):
        candidate = payload["pagination"].get("next")
    if not candidate and isinstance(payload.get("data"), dict):
        candidate = payload["data"].get("next")

    if not isinstance(candidate, str) or not candidate.strip():
        return None

    return urljoin(current_url, candidate.strip())

UPLOAD_TARGET_TABLES = [
    {"value": "universities", "label": "Universities"},
    {"value": "colleges", "label": "Colleges"},
    {"value": "courses", "label": "Courses"},
    {"value": "entrance_exams", "label": "Entrance Exams"},
]


def get_supabase_client():
    url = os.getenv("SUPABASE_URL", "").strip()
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.getenv("SUPABASE_ANON_KEY", "").strip()

    if not url or not key:
        return None

    return create_client(url, key)


def get_postgres_connection_url():
    return os.getenv("SUPABASE_POSTGRES_URL", "").strip() or os.getenv("DATABASE_URL", "").strip()


def convert_excel_to_records(uploaded_file):
    if pd is None:
        raise RuntimeError("pandas is not installed. Install requirements to process Excel uploads.")

    excel_bytes = uploaded_file.read()
    if not excel_bytes:
        raise ValueError("The uploaded file is empty.")

    workbook = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=None)
    if not workbook:
        raise ValueError("No sheets found in the uploaded Excel file.")

    records = []
    for sheet_name, dataframe in workbook.items():
        cleaned_dataframe = dataframe.where(pd.notnull(dataframe), None)
        for row_index, row in cleaned_dataframe.iterrows():
            payload = {}
            for column_name, value in row.items():
                normalized_column = str(column_name).strip()
                if not normalized_column:
                    continue
                payload[normalized_column] = value

            if not payload:
                continue

            records.append(
                {
                    "file_name": uploaded_file.filename,
                    "sheet_name": str(sheet_name),
                    "row_number": int(row_index) + 2,
                    "payload": payload,
                }
            )

    if not records:
        raise ValueError("The uploaded Excel file has no data rows to store.")

    return records


def insert_records_in_batches(supabase_client, table_name, records, batch_size=500):
    inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        supabase_client.table(table_name).insert(batch).execute()
        inserted += len(batch)
    return inserted


def insert_records_via_postgres(connection_url, table_name, records):
    if connect is None or Json is None or execute_values is None:
        raise RuntimeError("psycopg2-binary is not installed. Install requirements to use Postgres upload.")

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("Invalid table name. Use letters, numbers, and underscore only.")

    rows = [
        (
            item["file_name"],
            item["sheet_name"],
            item["row_number"],
            Json(item["payload"]),
        )
        for item in records
    ]

    with connect(connection_url) as conn:
        with conn.cursor() as cursor:
            query = (
                f"INSERT INTO {table_name} (file_name, sheet_name, row_number, payload) "
                "VALUES %s"
            )
            execute_values(cursor, query, rows, page_size=500)

    return len(rows)


def ensure_upload_table_exists(connection_url, table_name):
    if connect is None:
        raise RuntimeError("psycopg2-binary is not installed. Install requirements to use Postgres upload.")

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError("Invalid table name. Use letters, numbers, and underscore only.")

    with connect(connection_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id bigserial PRIMARY KEY,
                    file_name text NOT NULL,
                    sheet_name text NOT NULL,
                    row_number integer NOT NULL,
                    payload jsonb NOT NULL,
                    uploaded_at timestamptz DEFAULT now()
                )
                """
            )


UNIVERSITIES_DATA = [
    {
        "slug": "savitribai-phule-pune-university",
        "name": "Savitribai Phule Pune University",
        "location": "Pune",
        "state": "Maharashtra",
        "type": "Government",
        "stream": "General",
        "nirf": "19",
        "logo_url": "/static/logo.png",
    },
    {
        "slug": "university-of-mumbai",
        "name": "University of Mumbai",
        "location": "Mumbai",
        "state": "Maharashtra",
        "type": "Government",
        "stream": "General",
        "nirf": "45",
        "logo_url": "/static/logo.png",
    },
    {
        "slug": "rtm-nagpur-university",
        "name": "Rashtrasant Tukadoji Maharaj Nagpur University",
        "location": "Nagpur",
        "state": "Maharashtra",
        "type": "Government",
        "stream": "General",
        "nirf": "74",
        "logo_url": "/static/logo.png",
    },
    {
        "slug": "symbiosis-international",
        "name": "Symbiosis International (Deemed University)",
        "location": "Pune",
        "state": "Maharashtra",
        "type": "Deemed",
        "stream": "Management",
        "nirf": "17",
        "logo_url": "/static/logo.png",
    },
    {
        "slug": "mit-wpu",
        "name": "MIT World Peace University",
        "location": "Pune",
        "state": "Maharashtra",
        "type": "Private",
        "stream": "Technology",
        "nirf": "96",
        "logo_url": "/static/logo.png",
    },
    {
        "slug": "nmims-mumbai",
        "name": "NMIMS University",
        "location": "Mumbai",
        "state": "Maharashtra",
        "type": "Private",
        "stream": "Management",
        "nirf": "49",
        "logo_url": "/static/logo.png",
    },
]


COLLEGES_DATA = [
    {
        "name": "COEP Technological University",
        "state": "Maharashtra",
        "city": "Pune",
        "type": "Government",
        "stream": "Engineering",
        "nirf": "73",
        "logo_url": "/static/logo.png",
        "source_url": "https://www.coep.org.in",
    },
    {
        "name": "VJTI Mumbai",
        "state": "Maharashtra",
        "city": "Mumbai",
        "type": "Government",
        "stream": "Engineering",
        "nirf": "101-150",
        "logo_url": "/static/logo.png",
        "source_url": "https://vjti.ac.in",
    },
    {
        "name": "Fergusson College",
        "state": "Maharashtra",
        "city": "Pune",
        "type": "Autonomous",
        "stream": "Arts & Science",
        "nirf": "58",
        "logo_url": "/static/logo.png",
        "source_url": "https://fergusson.edu",
    },
    {
        "name": "St. Xavier's College",
        "state": "Maharashtra",
        "city": "Mumbai",
        "type": "Private",
        "stream": "Arts & Science",
        "nirf": "89",
        "logo_url": "/static/logo.png",
        "source_url": "https://xaviers.edu",
    },
    {
        "name": "KJ Somaiya College of Engineering",
        "state": "Maharashtra",
        "city": "Mumbai",
        "type": "Private",
        "stream": "Engineering",
        "nirf": "151-200",
        "logo_url": "/static/logo.png",
        "source_url": "https://kjsit.somaiya.edu",
    },
    {
        "name": "Ness Wadia College",
        "state": "Maharashtra",
        "city": "Pune",
        "type": "Aided",
        "stream": "Commerce",
        "nirf": "101-150",
        "logo_url": "/static/logo.png",
        "source_url": "https://nesswadia.edu",
    },
]


ARTICLES = [
    {
        "id": 1,
        "title": "Career in Engineering After 12th",
        "desc": "Modern civil engineering is being reshaped by digital twins and smart materials. Engineers now deploy sensor-embedded concrete that self-reports stress fractures before they become critical failures. AI-driven structural analysis reduces design iteration cycles from weeks to hours. Modular construction techniques are slashing build times on urban housing projects globally. Sustainability mandates are pushing firms to adopt low-carbon steel and recycled aggregates at scale. The convergence of BIM software and real-time IoT monitoring is creating infrastructure that actively communicates its health. The future of engineering is not just about building structures, but about creating intelligent systems that adapt and evolve with the needs of society. As we look ahead, engineers will play a pivotal role in designing resilient cities, developing renewable energy solutions, and pioneering innovations that will shape the world for generations to come.",
        "category": "engineering",
        "href": "engineering-details.html",
    },
    {
        "id": 2,
        "title": "Medical Careers Without MBBS",
        "desc": "Precision medicine tailors treatment to an individual's genetic blueprint, moving healthcare away from one-size-fits-all protocols. Advances in whole-genome sequencing have made it possible to predict disease susceptibility decades before symptoms appear. Oncologists now match cancer therapies to specific tumor mutations rather than organ of origin. Pharmacogenomics is reducing adverse drug reactions by identifying patients who metabolize medications differently. Liquid biopsies—detecting cancer DNA in the bloodstream—are enabling earlier diagnosis with a simple blood draw. The integration of AI pathology tools is accelerating rare-disease diagnosis that once took years.Best alternatives like BDS, BAMS, Nursing & more.",
        "category": "medical",
        "href": "medical-details.html",
    },
    {
        "id": 3,
        "title": "MBA vs PGDM - Which is Better?",
        "desc": "Compare syllabus, colleges, fees and placements.The shift to hybrid work has fundamentally altered how managers build culture, accountability, and trust. Research shows asynchronous communication improves deep-work productivity but risks eroding spontaneous collaboration. Effective leaders now design explicit rituals—weekly video stand-ups, virtual coffee chats—to replicate hallway serendipity. Performance measurement is migrating from input metrics (hours logged) to outcome metrics (deliverables completed). Psychological safety has emerged as the single strongest predictor of high-performing remote teams. Organizations investing in digital-first documentation report faster onboarding and fewer knowledge silos across time zones.",
        "category": "management",
        "href": "mba-details.html",
    },
    {
        "id": 4,
        "title": "Top Government Jobs After Graduation",
        "desc": "SSC, Banking, UPSC, State services explained.Governments worldwide are deploying technology platforms to streamline citizen services and cut bureaucratic friction. Estonia's digital identity system allows residents to vote, file taxes, and access medical records entirely online. AI-driven permit processing in Singapore has reduced approval wait times from months to days. Open data mandates are enabling civic technologists to build tools that hold public officials accountable. Challenges remain around digital exclusion—millions of citizens lack the connectivity or literacy to benefit. Cybersecurity frameworks for critical national infrastructure are being stress-tested as state-sponsored attacks grow more sophisticated. The future of government jobs will require a blend of public service ethos and digital fluency to navigate this evolving landscape.",
        "category": "government",
        "href": "government-details.html",
    },
    {
        "id": 5,
        "title": "Future Skills Engineers Must Learn",
        "desc": "AI, Data Science, Cyber Security & Automation.Mechanical engineering is one of the broadest disciplines, covering the design and analysis of everything from microelectromechanical systems to jet turbines. Professionals apply thermodynamics, fluid mechanics, and materials science to solve real-world problems in automotive, aerospace, energy, and consumer products. CAD proficiency—SolidWorks, CATIA, or NX—combined with FEA simulation skills defines the modern mechanical engineer's toolkit. The electric vehicle revolution is creating enormous demand for engineers specializing in battery thermal management, powertrain design, and lightweight structures. Additive manufacturing is transforming prototyping and low-volume production, requiring engineers to rethink design constraints that existed for centuries. Chartered and professional engineering accreditation significantly enhances career mobility across international markets.",
        "category": "engineering",
        "href": "future-skills-details.html",
    },
    {
        "id": 6,
        "title": "Careers in Digital Marketing",
        "desc": "SEO, Social Media, Performance Marketing & scope.Human resource management sits at the strategic center of modern organizations, responsible for talent acquisition, development, retention, and compliance. The discipline has evolved far beyond hiring and payroll—today's HR leaders own diversity and inclusion strategy, organizational design, and workforce analytics. People analytics tools allow HR professionals to predict attrition, measure engagement, and quantify the ROI of learning and development programs. Employment law expertise is non-negotiable as organizations navigate remote work regulations, non-compete enforcement, and AI-in-hiring compliance. HR business partner roles embed professionals directly within business units, aligning people strategy with commercial objectives in real time. A CIPD, SHRM, or equivalent professional qualification signals credibility, though demonstrated commercial impact matters most at the senior level. The future of HR will require a blend of emotional intelligence, data literacy, and strategic acumen to build resilient organizations in an era of rapid change.",
        "category": "management",
        "href": "digital-marketing-details.html",
    },
    {
        "id": 7,
        "title": "Careers in Aviation",
        "desc": "Explore careers as a pilot, cabin crew, or in aviation management.The aviation industry accounts for roughly 2.5% of global CO₂ emissions and faces mounting pressure to decarbonize. Sustainable aviation fuels (SAF) derived from agricultural waste can cut lifecycle emissions by up to 80% compared to fossil jet fuel. Airbus and Boeing are both testing hydrogen-powered demonstrators targeting commercial entry before 2035. Electric regional aircraft are already flying short routes in Scandinavia, proving the technology's near-term viability. Aerodynamic innovations—blended wing bodies and natural laminar flow wings—promise double-digit efficiency gains. Carbon offset programs, while controversial, are bridging the gap until next-generation propulsion matures.",
        "category": "aviation",
        "href": "aviation-details.html",
    },
    {
        "id": 8,
        "title": "Careers in Law",
        "desc": "Discover the various fields of law and career paths for law graduates.Artificial intelligence is automating contract review, due diligence, and legal research tasks that once consumed thousands of billable hours. Large language models can surface relevant case law across jurisdictions in seconds, dramatically leveling the playing field for smaller firms. Predictive analytics tools now estimate litigation outcomes with accuracy that rivals experienced practitioners. Ethical questions are intensifying around AI-generated legal advice and the unauthorized practice of law. Courts in multiple countries have begun issuing guidance on the use of AI-drafted filings, requiring explicit disclosure. The legal profession is responding with new bar association frameworks that balance innovation with client protection. The future of lawyering will require a blend of traditional legal expertise and digital literacy to navigate this rapidly evolving landscape.",
        "category": "law",
        "href": "law-details.html",
    },
    {
        "id": 9,
        "title": "Careers in Hotel Management",
        "desc": "Explore the hospitality industry and careers in hotel management.Project managers are the connective tissue of organizations, responsible for delivering complex initiatives on time, within budget, and to agreed quality standards. The PMP certification from PMI and the PRINCE2 framework are globally recognized credentials that open doors across industries from construction to software. Agile and Scrum methodologies have reshaped project management in technology firms, privileging iterative delivery over rigid waterfall planning. Risk identification and stakeholder communication are consistently cited as the competencies that separate average from exceptional project managers. Software tools—Jira, Asana, MS Project—are table stakes; the real differentiator is judgment under uncertainty and the ability to navigate competing priorities. Senior project managers frequently transition into program management, where they oversee portfolios of interdependent projects at the organizational level.",
        "category": "management",
        "href": "hotel-management-details.html",
    },
    {
        "id": 10,
        "title": "Careers in Fashion Designing",
        "desc": "Learn about the creative world of fashion and design careers.Fashion designing blends artistic creativity with technical skill to shape how the world dresses. Designers work across haute couture, ready-to-wear, and fast fashion, each demanding distinct competencies. Core skills include sketching, pattern making, textile knowledge, and proficiency with CAD tools like CLO 3D. Top fashion capitals—Milan, Paris, New York, and Mumbai—remain hotbeds of opportunity, though digital-first brands are opening remote roles globally. Sustainable fashion is the field's fastest-growing niche, with brands under intense pressure to reduce waste and ethical sourcing. A portfolio, internship experience, and a strong social media presence matter as much as a formal degree. The future of fashion design will require a blend of creativity, technical expertise, and a deep understanding of consumer trends to succeed in this dynamic industry.",
        "category": "creative",
        "href": "fashion-designing-details.html",
    },
    {
        "id": 11,
        "title": "Careers in Data Science",
        "desc": "Dive into the world of data and learn about careers in data science.Electrical engineers design the systems that generate, transmit, and consume power—and increasingly, the electronics embedded in every device we use. Power electronics specialists are at the heart of the renewable energy transition, designing inverters for solar farms and high-voltage direct current transmission lines. Embedded systems engineers program microcontrollers and FPGAs that run everything from medical implants to automotive safety systems. Semiconductor design, dominated by companies like TSMC, NVIDIA, and ASML, offers some of the highest-paying and technically demanding roles in engineering. Signal processing expertise is foundational for careers in telecommunications, radar, audio engineering, and medical imaging. The Internet of Things is blurring boundaries between electrical and software engineering, rewarding professionals who are comfortable in both domains.",
        "category": "technology",
        "href": "data-science-details.html",
    },
    {
        "id": 12,
        "title": "Careers in Blockchain",
        "desc": "Explore the revolutionary technology of blockchain and its career prospects.Blockchain technology underpins cryptocurrencies but its applications now span supply chain, healthcare records, digital identity, and smart contracts. Developers fluent in Solidity, Rust, or Go are building decentralized applications that remove the need for central intermediaries. Financial institutions and logistics giants are hiring blockchain architects to redesign back-office settlement systems. NFT marketplaces and DeFi protocols created an entirely new layer of product and legal careers over the past four years. Regulatory clarity—advancing in the EU and US—is opening institutional capital to the sector and stabilizing job demand. Security auditing is a premium niche: smart contract vulnerabilities have cost the industry billions, driving urgent demand for skilled auditors. The future of blockchain careers will require a blend of cryptographic expertise, software engineering, and an understanding of decentralized governance models.",
        "category": "technology",
        "href": "blockchain-details.html",
    },
    {
        "id": 13,
        "title": "Careers in Machine Learning",
        "desc": "Get into the exciting field of AI and Machine Learning.Machine learning engineers design, train, and deploy the models that power recommendation engines, medical diagnostics, autonomous vehicles, and generative AI. The role demands fluency in deep learning frameworks such as PyTorch and TensorFlow, along with strong mathematical foundations in linear algebra and probability. MLOps—the discipline of deploying and monitoring models in production—has emerged as a critical specialization as companies struggle to move prototypes into reliable systems. Research roles at labs like DeepMind, OpenAI, and academic institutions push the frontier of model architecture and alignment. Entry paths include postgraduate degrees, Kaggle competition rankings, and open-source contributions to prominent repositories. The field evolves so rapidly that continuous self-study is non-negotiable for long-term career health.",
        "category": "technology",
        "href": "machine-learning-details.html",
    },
    {
        "id": 14,
        "title": "Careers in Cloud Computing",
        "desc": "Learn about cloud technologies and the career opportunities in this domain.Cloud computing has become the backbone of modern enterprise IT, creating sustained demand for architects, DevOps engineers, and security specialists. AWS, Microsoft Azure, and Google Cloud certifications serve as practical credentials that hiring managers actively prioritize over academic qualifications. Infrastructure-as-code tools—Terraform, Ansible, Kubernetes—are now baseline expectations in most mid-to-senior cloud roles. FinOps, the practice of optimizing cloud spending, is an emerging specialty as organizations discover they are overpaying for underutilized resources. Multi-cloud strategy skills are increasingly valuable as enterprises diversify vendor dependencies after high-profile outages. Remote work is the default in cloud roles, with distributed teams spanning multiple continents managing global infrastructure from laptops",
        "category": "technology",
        "href": "cloud-computing-details.html",
    },
    {
        "id": 15,
        "title": "Careers in Architecture",
        "desc": "Discover the field of architecture and the path to becoming an architect.Architecture merges structural engineering, environmental science, and visual design to shape the spaces where people live, work, and gather. Licensure requires completing an accredited degree, a multi-year internship, and passing the Architect Registration Examination in most jurisdictions. BIM software—primarily Autodesk Revit and ArchiCAD—has become the industry standard, replacing hand drafting entirely in commercial practice. Sustainable design and LEED certification expertise are increasingly required as building codes tighten around energy efficiency globally. Parametric design tools like Grasshopper allow architects to generate and test complex organic forms that were impossible to build a generation ago. Interior design, urban planning, and landscape architecture offer adjacent career paths for those whose interests extend beyond building envelopes.",
        "category": "creative",
        "href": "architecture-details.html",
    },
    {
        "id": 16,
        "title": "Careers in Robotics",
        "desc": "Explore the exciting field of robotics and automation.Humanoid robots have crossed from science fiction into production lines, with Tesla, Figure, and Agility Robotics deploying bipedal machines in warehouses. Designed to operate in spaces built for humans, these robots can climb stairs, handle irregular objects, and work alongside people without cage barriers. Foundation models trained on vast human motion datasets allow robots to generalize new tasks from a handful of demonstrations. Battery energy density remains the key bottleneck limiting operational runtime to four to eight hours. Labor economists are hotly debating displacement versus augmentation effects, with early data suggesting net job creation in robot-adjacent roles. The next frontier is dexterous manipulation—teaching robots the fine motor skills needed in surgery and electronics assembly.",
        "category": "robotics",
        "href": "robotics-details.html",
    },
    {
        "id": 17,
        "title": "Careers in Cybersecurity",
        "desc": "Protect digital systems and data from cyber threats.Ransomware attacks cost organizations globally an estimated $20 billion annually, with healthcare and critical infrastructure the most frequent targets. Nation-state groups now license ransomware-as-a-service toolkits to criminal affiliates, blurring the line between geopolitical conflict and organized crime. Zero-trust architecture—which assumes no user or device is inherently trusted—is fast becoming the security baseline for enterprise networks. Multi-factor authentication and endpoint detection response tools have proven to reduce breach severity significantly. Cyber insurance premiums have tripled in three years as carriers tighten coverage terms and exclusions. International cooperation on ransomware attribution remains hampered by jurisdictional and diplomatic obstacles.",
        "category": "cybersecurity",
        "href": "cybersecurity-details.html",
    },
    {
        "id": 18,
        "title": "Careers in UI/UX Design",
        "desc": "Design user-friendly and engaging digital experiences.Accessibility has shifted from a compliance checkbox to a recognized driver of product quality and market reach. WCAG 3.0 guidelines are expanding coverage beyond screen readers to include cognitive load, motion sensitivity, and low-literacy users. Inclusive design sprints that involve disabled users from day one consistently uncover usability issues invisible to homogeneous teams. Apple's Dynamic Type and Google's Material You demonstrate how accessibility features—larger text, high contrast modes—become beloved by all users. Legal exposure is rising as ADA and European Accessibility Act enforcement actions against digital products multiply. Designers who can audit and remediate accessibility issues command a measurable salary premium in the current market.",
        "category": "ui-ux-design",
        "href": "ui-ux-design-details.html",
    },
    {
        "id": 19,
        "title": "Careers in Renewable Energy",
        "desc": "Work on sustainable energy solutions for the future.Grid-scale battery storage is the missing piece that makes intermittent wind and solar dispatchable around the clock. Lithium iron phosphate (LFP) batteries have seen a 90% cost reduction over the past decade, making utility-scale projects economically compelling. Australia's Hornsdale Power Reserve demonstrated that large batteries could stabilize grid frequency faster than any conventional power plant. Flow batteries and compressed air storage are emerging as complementary technologies for multi-day energy buffering. Vehicle-to-grid (V2G) programs are turning electric car fleets into distributed storage assets during peak demand. Analysts project that global battery storage capacity will exceed 1,500 GWh by 2030, fundamentally changing how grids are operated. The transition to renewable energy will require a massive expansion of the energy workforce, with new roles in project development, grid integration, and maintenance of advanced energy systems.",
        "category": "renewable-energy",
        "href": "renewable-energy-details.html",
    },
    {
        "id": 20,
        "title": "Careers in Genetic Engineering",
        "desc": "Explore the fascinating world of genetic manipulation and its applications.CRISPR-Cas9 gene editing has moved from a laboratory curiosity to an approved therapeutic platform in under a decade. The FDA's 2023 approval of Casgevy for sickle cell disease marked a historic milestone for in-vivo genetic medicine. Scientists are now developing base editing and prime editing variants that make single-letter DNA corrections with minimal off-target effects. Agricultural applications include drought-resistant crops and disease-tolerant livestock engineered without introducing foreign DNA, sidestepping many regulatory hurdles. Ethical debates around germline editing—changes that would be inherited by future generations—remain unresolved internationally. The cost of CRISPR therapies, currently exceeding $2 million per patient, is the primary barrier to broad adoption. As the technology matures, we can expect to see a proliferation of genetic engineering careers in research, clinical development, bioinformatics, and regulatory affairs.",
        "category": "genetic-engineering",
        "href": "genetic-engineering-details.html",
    },
]


CATEGORIES = [
    {"value": "all", "label": "All"},
    {"value": "engineering", "label": "Engineering"},
    {"value": "medical", "label": "Medical"},
    {"value": "management", "label": "Management"},
    {"value": "government", "label": "Government"},
    {"value": "aviation", "label": "Aviation"},
    {"value": "law", "label": "Law"},
    {"value": "creative", "label": "Creative"},
    {"value": "technology", "label": "Technology"},
    {"value": "robotics", "label": "Robotics"},
    {"value": "cybersecurity", "label": "Cybersecurity"},
    {"value": "ui-ux-design", "label": "UI/UX Design"},
    {"value": "renewable-energy", "label": "Renewable Energy"},
    {"value": "genetic-engineering", "label": "Genetic Engineering"},
]


def get_article_by_id(article_id):
    return next((article for article in ARTICLES if article["id"] == article_id), None)


def build_article_teaser(text, max_len=120):
    clean = " ".join((text or "").split())
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 3].rstrip() + "..."


def build_article_paragraphs(text):
    # Turn long one-line content into readable chunks for detail page rendering.
    sentences = [part.strip() for part in (text or "").split(".") if part.strip()]
    if not sentences:
        return ["Content will be updated soon."]

    paragraphs = []
    bucket = []
    for idx, sentence in enumerate(sentences, start=1):
        bucket.append(sentence + ".")
        if len(bucket) == 3 or idx == len(sentences):
            paragraphs.append(" ".join(bucket))
            bucket = []
    return paragraphs


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/blog")
def blog():
    return render_template("blogs.html")  # Placeholder


@app.route("/epaper")
def epaper():
    return render_template("epaper.html")


@app.route("/api/epaper-feed")
def epaper_feed():
    base = VMADMIN_BASE_URL
    if not base:
        return jsonify([])

    source_paths = ["/api/news", "/news", "/api/epapers", "/api/editions"]

    for path in source_paths:
        current_url = f"{base}{path}"
        combined_items = []
        page_guard = 0

        while current_url and page_guard < 25:
            payload = fetch_remote_json(current_url)
            if payload is None:
                combined_items = []
                break

            items = extract_items(payload)
            if items:
                combined_items.extend(items)
                current_url = extract_next_url(payload, current_url)
            else:
                if isinstance(payload, list):
                    combined_items.extend(payload)
                current_url = None

            page_guard += 1

        if combined_items:
            return jsonify(combined_items)

    return jsonify([])

@app.route("/admin")
def admin():
    return render_template("epaperadmin.html")


@app.route("/api/vmadmin/<path:subpath>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def vmadmin_proxy(subpath):
    if not VMADMIN_BASE_URL:
        return jsonify({"error": "VMADMIN_BASE_URL is not configured."}), 500

    upstream_url = f"{VMADMIN_BASE_URL}/{subpath.lstrip('/')}"
    if request.query_string:
        upstream_url = f"{upstream_url}?{request.query_string.decode('utf-8', errors='ignore')}"

    passthrough_headers = {
        "Accept": request.headers.get("Accept", "application/json"),
        "User-Agent": "vm-main-website/1.0",
    }
    if request.headers.get("Authorization"):
        passthrough_headers["Authorization"] = request.headers["Authorization"]
    if request.headers.get("Content-Type"):
        passthrough_headers["Content-Type"] = request.headers["Content-Type"]

    body = request.get_data() if request.method in {"POST", "PUT", "PATCH"} else None
    proxy_request = Request(
        upstream_url,
        data=body,
        headers=passthrough_headers,
        method=request.method,
    )

    try:
        with urlopen(proxy_request, timeout=20) as response:
            payload = response.read()
            status_code = response.getcode()
            content_type = response.headers.get("Content-Type", "application/json")
            return payload, status_code, {"Content-Type": content_type}
    except HTTPError as exc:
        error_payload = exc.read()
        content_type = exc.headers.get("Content-Type", "application/json") if exc.headers else "application/json"
        return error_payload, exc.code, {"Content-Type": content_type}
    except URLError:
        return jsonify({"error": "Unable to reach VM admin service."}), 502



@app.route("/universities")
def universities():
    states = sorted({item["state"] for item in UNIVERSITIES_DATA})
    cities = sorted({item["location"] for item in UNIVERSITIES_DATA})
    types = sorted({item["type"] for item in UNIVERSITIES_DATA})
    streams = sorted({item["stream"] for item in UNIVERSITIES_DATA})
    return render_template(
        "universities.html",
        universities=UNIVERSITIES_DATA,
        states=states,
        cities=cities,
        types=types,
        streams=streams,
    )


@app.route("/universities/<slug>")
def university_detail(slug):
    university = next((item for item in UNIVERSITIES_DATA if item["slug"] == slug), None)
    if university is None:
        return redirect(url_for("universities"))
    return render_template("universities.html", universities=[university], states=[], cities=[], types=[], streams=[])


@app.route("/colleges")
def colleges():
    states = sorted({item["state"] for item in COLLEGES_DATA})
    cities = sorted({item["city"] for item in COLLEGES_DATA})
    types = sorted({item["type"] for item in COLLEGES_DATA})
    streams = sorted({item["stream"] for item in COLLEGES_DATA})
    return render_template(
        "colleges.html",
        colleges=COLLEGES_DATA,
        states=states,
        cities=cities,
        types=types,
        streams=streams,
    )


@app.route("/courses")
def courses():
    return render_template("courses.html")


@app.route("/entrance-exams")
def exams():
    return render_template("entrance-exams.html")  # Placeholder


@app.route("/mock-exams")
def mock_exams():
    # Dynamic lists to populate the Jinja2 loops
    exams = ["JEE", "NEET", "MHT-CET", "CAT", "GATE", "CLAT"]
    streams = [
        {"name": "Engineering", "class": "engineering", "icon": "fa-microchip"},
        {"name": "Medical", "class": "medical", "icon": "fa-user-md"},
        {"name": "Management", "class": "management", "icon": "fa-chart-pie"},
        {"name": "Banking", "class": "banking", "icon": "fa-university"}
    ]
    return render_template("mock_exams.html", exams=exams, streams=streams)


@app.route("/cutoffs")
def cutoffs():
    return render_template("cutoffs.html")


@app.route("/fyjc_rank")
def fyjc_rank():
    return render_template("fyjc_rank.html")


@app.route("/admissions")
def admissions():
    return render_template("admissions.html")  # Placeholder

@app.route("/news")
def news():
    return render_template("news.html")
@app.route('/exam-updates')
def home():
    # This looks inside the 'templates' folder automatically
    return render_template('exam-updates.html')

@app.route("/articles")
@app.route("/career-articles")
def articles():
    category = request.args.get("category", "all").strip()
    query = request.args.get("q", "").strip().lower()

    valid_categories = {item["value"] for item in CATEGORIES}
    if category not in valid_categories:
        category = "all"

    filtered_articles = ARTICLES
    if category != "all":
        filtered_articles = [
            article for article in filtered_articles if article["category"] == category
        ]
    if query:
        filtered_articles = [
            article
            for article in filtered_articles
            if query in article["title"].lower() or query in article["desc"].lower()
        ]

    list_articles = [
        {
            **article,
            "desc": build_article_teaser(article.get("desc", "")),
        }
        for article in filtered_articles
    ]

    return render_template(
        "articles.html",
        articles=list_articles,
        categories=CATEGORIES,
        active_category=category,
        query=query,
        total=len(filtered_articles),
    )


@app.route("/articles/<int:article_id>")
def article_detail(article_id):
    article = get_article_by_id(article_id)
    if article is None:
        return redirect(url_for("articles"))
    article_detail_data = {
        **article,
        "paragraphs": build_article_paragraphs(article.get("desc", "")),
    }
    return render_template("article_detail.html", article=article_detail_data)


@app.route("/api/articles")
def api_articles():
    category = request.args.get("category", "all").strip()
    query = request.args.get("q", "").strip().lower()

    valid_categories = {item["value"] for item in CATEGORIES}
    if category not in valid_categories:
        category = "all"

    result = ARTICLES
    if category != "all":
        result = [article for article in result if article["category"] == category]
    if query:
        result = [
            article
            for article in result
            if query in article["title"].lower() or query in article["desc"].lower()
        ]

    return jsonify({"count": len(result), "articles": result})


@app.route('/stories')
@app.route('/student-stories')
def student_stories():
    # Flask looks in the 'templates' folder by default
    return render_template('student-stories.html')


@app.route('/submit_story')
@app.route('/submit-story')
def submit_story():
    return render_template('submit_story.html')


@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if request.method == "POST":
        required_fields = [
            "u_name",
            "u_mobile",
            "u_email",
            "u_designation",
            "u_feedback",
        ]
        missing_fields = [field for field in required_fields if not request.form.get(field, "").strip()]

        if missing_fields:
            flash("Please fill all required fields before submitting.", "error")
            return render_template("feedback.html")

        flash("Feedback submitted successfully. Thank you!", "success")
        return redirect(url_for("feedback"))

    return render_template("feedback.html")


@app.route("/chatbot")
def chatbot():
    return render_template("chatbot.html")


@app.route("/guideme", methods=["GET", "POST"])
@app.route("/guide-me", methods=["GET", "POST"])
def guide_me():
    if request.method == "POST":
        required_fields = ["full_name", "whatsapp", "email", "address", "requirement_type"]
        missing_fields = [field for field in required_fields if not request.form.get(field, "").strip()]

        if missing_fields:
            flash("Please complete all required Guide Me form fields.", "error")
            return render_template("GuideMe1.html")

        flash("Guide Me form submitted successfully.", "success")
        return redirect(url_for("guide_me"))

    return render_template("GuideMe1.html")

@app.route('/refund-policy')
def refund_policy():
    return render_template('refund.html')


@app.route("/excel-upload", methods=["GET", "POST"])
def excel_upload():
    allowed_tables = {item["value"] for item in UPLOAD_TARGET_TABLES}
    default_table = os.getenv("SUPABASE_EXCEL_TABLE", "universities").strip() or "universities"
    if default_table not in allowed_tables:
        default_table = "universities"

    supabase_client = get_supabase_client()
    postgres_connection_url = get_postgres_connection_url()
    configured = supabase_client is not None or bool(postgres_connection_url)
    connection_mode = "postgres-url" if postgres_connection_url else "supabase-api"
    selected_table = default_table

    if request.method == "POST":
        selected_table = request.form.get("target_table", default_table).strip()
        if selected_table not in allowed_tables:
            flash("Please choose a valid target table.", "error")
            return render_template(
                "excel_upload.html",
                configured=configured,
                table_name=default_table,
                selected_table=default_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        if not configured:
            flash(
                "Supabase is not configured. Set SUPABASE_POSTGRES_URL (or DATABASE_URL), or set SUPABASE_URL with SUPABASE_SERVICE_ROLE_KEY.",
                "error",
            )
            return render_template(
                "excel_upload.html",
                configured=False,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        uploaded_file = request.files.get("excel_file")
        if uploaded_file is None or not uploaded_file.filename:
            flash("Please choose an Excel file to upload.", "error")
            return render_template(
                "excel_upload.html",
                configured=True,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        if not uploaded_file.filename.lower().endswith((".xlsx", ".xls")):
            flash("Invalid file type. Please upload an .xlsx or .xls file.", "error")
            return render_template(
                "excel_upload.html",
                configured=True,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        try:
            records = convert_excel_to_records(uploaded_file)
            if postgres_connection_url:
                ensure_upload_table_exists(postgres_connection_url, selected_table)
                inserted_rows = insert_records_via_postgres(postgres_connection_url, selected_table, records)
            else:
                inserted_rows = insert_records_in_batches(supabase_client, selected_table, records)
        except Exception as exc:
            flash(f"Upload failed: {exc}", "error")
            return render_template(
                "excel_upload.html",
                configured=True,
                table_name=selected_table,
                selected_table=selected_table,
                upload_targets=UPLOAD_TARGET_TABLES,
                connection_mode=connection_mode,
            )

        flash(f"Upload successful. Inserted {inserted_rows} row(s) into {selected_table}.", "success")
        return redirect(url_for("excel_upload"))

    return render_template(
        "excel_upload.html",
        configured=configured,
        table_name=selected_table,
        selected_table=selected_table,
        upload_targets=UPLOAD_TARGET_TABLES,
        connection_mode=connection_mode,
    )


if __name__ == "__main__":
    app.run(debug=True)
