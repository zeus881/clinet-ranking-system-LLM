const API_URL = "http://127.0.0.1:5000/companies";

const DETAIL_FIELDS = [
  ["industry", "Industry"],
  ["summary", "Summary"],
  ["website", "Website"],
];

const state = {
  companies: [],
  filteredCompanies: [],
  selectedCompanyId: null,
};

let elements = null;

function safeText(value, fallback = "N/A") {
  if (value === null || value === undefined) {
    return fallback;
  }

  const text = String(value).trim();
  return text || fallback;
}

function safeScore(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : 0;
}

function formatScore(value) {
  return `${safeScore(value).toFixed(1)}%`;
}

function createCompanyId(record, index) {
  return `${safeText(record.company_name, "company")}-${safeText(record.website, "site")}-${index}`;
}

function normalizeCompany(record, index) {
  const website = safeText(record.website, "");
  const fixedWebsite = website && !website.startsWith("http") ? `https://${website}` : website;

  return {
    id: createCompanyId(record, index),
    company_name: safeText(record.company_name, "Unknown Company"),
    website: safeText(fixedWebsite, "N/A"),
    industry: safeText(record.industry, "Other"),
    summary: safeText(record.summary, "No summary available."),
    score: safeScore(record.score),
    products: Array.isArray(record.products) ? record.products : [],
    product_specifications: safeText(record.product_specifications, ""),
    technologies: safeText(record.technologies, ""),
    price_range: safeText(record.price_range, ""),
    contact_email: safeText(record.contact_email, ""),
    phone: safeText(record.phone, ""),
  };
}

function sortCompaniesByScore(companies) {
  return [...companies].sort((left, right) => safeScore(right.score) - safeScore(left.score));
}

function filterCompaniesByName(companies, query) {
  const normalizedQuery = safeText(query, "").toLowerCase().trim();
  if (!normalizedQuery) {
    return [...companies];
  }

  return companies.filter((company) =>
    safeText(company.company_name, "").toLowerCase().includes(normalizedQuery)
  );
}

function calculateAverageScore(companies) {
  if (!companies.length) {
    return 0;
  }

  const total = companies.reduce((sum, company) => sum + safeScore(company.score), 0);
  return total / companies.length;
}

function buildWebsiteMarkup(website) {
  if (!website || website === "N/A") {
    return '<span class="table-link table-link--disabled">N/A</span>';
  }

  return `<a class="table-link" href="${website}" target="_blank" rel="noopener noreferrer">${website}</a>`;
}

function parseProductString(productStr) {
  if (!productStr || typeof productStr !== 'string') {
    return null;
  }

  const trimmed = productStr.trim();
  if (!trimmed) {
    return null;
  }

  // Split by common delimiters: comma, semicolon, or "and"
  const parts = trimmed
    .split(/[,;]\s*|\s+and\s+/i)
    .map(p => p.trim())
    .filter(Boolean);

  if (parts.length === 0) {
    return null;
  }

  // First part is the name, rest are features
  const name = parts[0];
  const features = parts.slice(1);

  return { name, features };
}

function parseSpecifications(specsStr) {
  if (!specsStr || typeof specsStr !== 'string') {
    return [];
  }

  const trimmed = specsStr.trim();
  if (!trimmed) {
    return [];
  }

  // Split by comma, semicolon, or period followed by space (but not decimal points)
  return trimmed
    .split(/[,;]\s*|\.\s+/)
    .map(s => s.trim())
    .filter(Boolean)
    .slice(0, 8); // Limit to 8 specs for readability
}

function parseTechnologies(techStr) {
  if (!techStr || typeof techStr !== 'string') {
    return [];
  }

  const trimmed = techStr.trim();
  if (!trimmed) {
    return [];
  }

  // Split by comma, semicolon, or "and"
  return trimmed
    .split(/[,;]\s*|\s+and\s+/i)
    .map(t => t.trim())
    .filter(Boolean)
    .slice(0, 12); // Limit to 12 technologies
}

function buildProductsSection(products, specifications, technologies) {
  if (!products || !Array.isArray(products)) {
    products = [];
  }

  const hasProducts = products && products.length > 0;
  const hasSpecs = specifications && specifications.trim().length > 0;
  const hasTechs = technologies && technologies.trim().length > 0;

  // If we have no data at all
  if (!hasProducts && !hasSpecs && !hasTechs) {
    return `
      <section class="detail-card detail-card--empty">
        <p class="detail-label">Products & Specifications</p>
        <p class="detail-value detail-value--muted">Product information not available in extracted data</p>
      </section>
    `;
  }

  let contentMarkup = "";

  // Products Section
  if (hasProducts) {
    const productMarkup = products
      .map(product => {
        let name = "";
        let features = [];

        // Handle object format
        if (typeof product === "object" && product !== null) {
          name = safeText(product.name || product.product || "", "Product");
          features = Array.isArray(product.features) 
            ? product.features.map(f => safeText(f, "")).filter(Boolean)
            : [];
        } 
        // Handle string format
        else if (typeof product === "string") {
          const parsed = parseProductString(product);
          if (parsed) {
            name = parsed.name;
            features = parsed.features;
          } else {
            name = safeText(product, "Product");
            features = [];
          }
        }

        if (!name) {
          return "";
        }

        return `
          <div class="product-card">
            <p class="product-card__name">${name}</p>
            ${features.length > 0 ? `
              <ul class="product-card__features">
                ${features.map(f => `<li>${f}</li>`).join("")}
              </ul>
            ` : ""}
          </div>
        `;
      })
      .filter(Boolean)
      .join("");

    if (productMarkup) {
      contentMarkup += `
        <div class="products-section">
          <p class="section-title">Products</p>
          <div class="product-grid">${productMarkup}</div>
        </div>
      `;
    }
  }

  // Specifications Section
  if (hasSpecs) {
    const specs = parseSpecifications(specifications);
    if (specs.length > 0) {
      const specsMarkup = specs
        .map(spec => `<li>${spec}</li>`)
        .join("");
      contentMarkup += `
        <div class="specifications-section">
          <p class="section-title">Specifications</p>
          <ul class="specifications-list">
            ${specsMarkup}
          </ul>
        </div>
      `;
    }
  }

  // Technologies Section
  if (hasTechs) {
    const techs = parseTechnologies(technologies);
    if (techs.length > 0) {
      const techsMarkup = techs
        .map(tech => `<span class="tech-tag">${tech}</span>`)
        .join("");
      contentMarkup += `
        <div class="technologies-section">
          <p class="section-title">Technologies</p>
          <div class="tech-tags-container">
            ${techsMarkup}
          </div>
        </div>
      `;
    }
  }

  return `
    <section class="detail-card detail-card--products">
      ${contentMarkup}
    </section>
  `;
}

function buildDetailSections(company) {
  const standardFields = DETAIL_FIELDS
    .map(([fieldName, label]) => {
      const value = safeText(company[fieldName], "");
      if (!value) {
        return "";
      }

      if (fieldName === "website") {
        return `
          <section class="detail-card">
            <p class="detail-label">${label}</p>
            <p class="detail-value">${buildWebsiteMarkup(value)}</p>
          </section>
        `;
      }

      return `
        <section class="detail-card">
          <p class="detail-label">${label}</p>
          <p class="detail-value">${value}</p>
        </section>
      `;
    })
    .filter(Boolean)
    .join("");

  const productsSection = buildProductsSection(company.products, company.product_specifications, company.technologies);
  return standardFields + productsSection;
}

function getElements() {
  if (elements) {
    return elements;
  }

  if (typeof document === "undefined") {
    return null;
  }

  elements = {
    totalCompanies: document.getElementById("totalCompanies"),
    topCompany: document.getElementById("topCompany"),
    topCompanyScore: document.getElementById("topCompanyScore"),
    averageScore: document.getElementById("averageScore"),
    tableBody: document.getElementById("companyTableBody"),
    statusMessage: document.getElementById("statusMessage"),
    searchInput: document.getElementById("searchInput"),
    heroBadge: document.getElementById("heroBadge"),
    detailCompanyName: document.getElementById("detailCompanyName"),
    detailWebsite: document.getElementById("detailWebsite"),
    detailScorePill: document.getElementById("detailScorePill"),
    detailContent: document.getElementById("detailContent"),
  };

  return elements;
}

function setStatus(message, type = "info") {
  const dom = getElements();
  if (!dom) {
    return;
  }

  dom.statusMessage.textContent = message;
  dom.statusMessage.classList.remove("is-error", "is-hidden");
  if (type === "error") {
    dom.statusMessage.classList.add("is-error");
  }
}

function clearStatus() {
  const dom = getElements();
  if (!dom) {
    return;
  }

  dom.statusMessage.textContent = "";
  dom.statusMessage.classList.add("is-hidden");
  dom.statusMessage.classList.remove("is-error");
}

function updateSummary(companies) {
  const dom = getElements();
  if (!dom) {
    return;
  }

  const topCompany = companies[0];
  dom.totalCompanies.textContent = String(companies.length);
  dom.topCompany.textContent = topCompany ? topCompany.company_name : "--";
  dom.topCompanyScore.textContent = topCompany
    ? `Score ${formatScore(topCompany.score)}`
    : "Waiting for ranked data";
  dom.averageScore.textContent = companies.length ? formatScore(calculateAverageScore(companies)) : "--";
  dom.heroBadge.textContent = companies.length ? "Live ranking data loaded" : "No ranked records";
}

function renderTable(companies) {
  const dom = getElements();
  if (!dom) {
    return;
  }

  if (!companies.length) {
    dom.tableBody.innerHTML = `
      <tr>
        <td colspan="4" class="empty-state">No companies matched the current search.</td>
      </tr>
    `;
    return;
  }

  dom.tableBody.innerHTML = companies
    .map((company, index) => {
      const isTopCompany = index === 0;
      const isSelected = company.id === state.selectedCompanyId;
      return `
        <tr
          class="company-row ${isTopCompany ? "company-row--top" : ""} ${isSelected ? "company-row--selected" : ""}"
          data-company-id="${company.id}"
          tabindex="0"
        >
          <td>
            <div class="company-cell">
              <span class="company-cell__name">${company.company_name}</span>
              <span class="company-cell__meta">${isTopCompany ? "Top ranked company" : "Click to inspect details"}</span>
            </div>
          </td>
          <td>${company.industry}</td>
          <td><span class="score-badge">${formatScore(company.score)}</span></td>
          <td>${buildWebsiteMarkup(company.website)}</td>
        </tr>
      `;
    })
    .join("");
}

function renderDetail(company) {
  const dom = getElements();
  if (!dom) {
    return;
  }

  if (!company) {
    dom.detailCompanyName.textContent = "Select a company";
    dom.detailWebsite.textContent = "Website unavailable";
    dom.detailWebsite.href = "#";
    dom.detailWebsite.classList.add("detail-website--disabled");
    dom.detailScorePill.textContent = "No selection";
    dom.detailContent.innerHTML = `
      <div class="detail-empty">
        Click a company row to open its complete structured profile.
      </div>
    `;
    return;
  }

  dom.detailCompanyName.textContent = company.company_name;
  dom.detailScorePill.textContent = `Score ${formatScore(company.score)}`;

  if (company.website && company.website !== "N/A") {
    dom.detailWebsite.textContent = company.website;
    dom.detailWebsite.href = company.website;
    dom.detailWebsite.classList.remove("detail-website--disabled");
  } else {
    dom.detailWebsite.textContent = "Website unavailable";
    dom.detailWebsite.href = "#";
    dom.detailWebsite.classList.add("detail-website--disabled");
  }

  dom.detailContent.innerHTML = `
    <section class="detail-highlight">
      <div>
        <p class="detail-label">Industry</p>
        <p class="detail-highlight__text">${company.industry}</p>
      </div>
      <div>
        <p class="detail-label">Score</p>
        <p class="detail-highlight__text">${formatScore(company.score)}</p>
      </div>
    </section>
    <div class="detail-grid">
      ${buildDetailSections(company)}
    </div>
  `;
}

function selectCompany(companyId) {
  state.selectedCompanyId = companyId;
  const company = state.filteredCompanies.find((item) => item.id === companyId)
    || state.companies.find((item) => item.id === companyId)
    || null;
  renderTable(state.filteredCompanies);
  renderDetail(company);
}

function applySearch(query) {
  state.filteredCompanies = filterCompaniesByName(state.companies, query);
  updateSummary(state.filteredCompanies);
  renderTable(state.filteredCompanies);

  if (!state.filteredCompanies.some((company) => company.id === state.selectedCompanyId)) {
    const nextCompany = state.filteredCompanies[0] || null;
    state.selectedCompanyId = nextCompany ? nextCompany.id : null;
    renderDetail(nextCompany);
    renderTable(state.filteredCompanies);
  }
}

function attachEventHandlers() {
  const dom = getElements();
  if (!dom) {
    return;
  }

  dom.searchInput.addEventListener("input", (event) => {
    applySearch(event.target.value);
  });

  dom.tableBody.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-company-id]");
    if (!row) {
      return;
    }

    selectCompany(row.dataset.companyId);
  });

  dom.tableBody.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") {
      return;
    }

    const row = event.target.closest("tr[data-company-id]");
    if (!row) {
      return;
    }

    event.preventDefault();
    selectCompany(row.dataset.companyId);
  });
}

function extractCompaniesFromPayload(payload) {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload.data)) {
    return payload.data;
  }

  if (Array.isArray(payload.companies)) {
    return payload.companies;
  }

  return [];
}

async function loadCompanies(fetchImpl = fetch) {
  setStatus("Loading ranked company data...");

  try {
    const response = await fetchImpl(API_URL);
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.message || "Unable to load companies from the API.");
    }

    const rawCompanies = extractCompaniesFromPayload(payload);

    state.companies = sortCompaniesByScore(rawCompanies.map(normalizeCompany));
    state.filteredCompanies = [...state.companies];

    updateSummary(state.filteredCompanies);

    if (!state.companies.length) {
      renderTable([]);
      renderDetail(null);
      setStatus(payload.message || "No ranked companies are available yet.", response.status === 202 ? "info" : "error");
      return [];
    }

    state.selectedCompanyId = state.companies[0].id;
    clearStatus();
    renderTable(state.filteredCompanies);
    renderDetail(state.companies[0]);
    return state.companies;
  } catch (error) {
    updateSummary([]);
    renderTable([]);
    renderDetail(null);
    setStatus(error.message || "Unable to connect to the company API.", "error");
    return [];
  }
}

function initDashboard() {
  if (typeof document === "undefined") {
    return;
  }

  getElements();
  attachEventHandlers();
  loadCompanies();
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initDashboard);
  } else {
    initDashboard();
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    API_URL,
    DETAIL_FIELDS,
    state,
    safeText,
    safeScore,
    formatScore,
    normalizeCompany,
    sortCompaniesByScore,
    filterCompaniesByName,
    calculateAverageScore,
    buildDetailSections,
    buildProductsSection,
    parseProductString,
    parseSpecifications,
    parseTechnologies,
  };
}
