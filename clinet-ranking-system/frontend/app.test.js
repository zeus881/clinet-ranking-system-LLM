const test = require("node:test");
const assert = require("node:assert/strict");

const {
  safeText,
  safeScore,
  normalizeListValue,
  normalizeListItems,
  normalizeProductObjects,
  normalizeCompany,
  sortCompaniesByScore,
  filterCompaniesByName,
  calculateAverageScore,
  extractCompanyRecordsFromPayload,
  buildProductGrid,
  buildDetailSections,
} = require("./app.js");

test("normalizeCompany maps the exact API schema and fills missing values safely", () => {
  const company = normalizeCompany(
    {
      company_name: "Acme Robotics",
      website: "https://acme.test",
      industry: null,
      products: ["Robots", "Sensors"],
      product_specifications: "",
      technologies: "Computer Vision, AI",
      price_range: null,
      contact_email: "",
      phone: "1234567890",
      address: undefined,
      description: "Industrial automation company",
      summary: null,
      score: "0.77",
    },
    0
  );

  assert.equal(company.company_name, "Acme Robotics");
  assert.equal(company.website, "https://acme.test");
  assert.equal(company.industry, "N/A");
  assert.equal(company.products, "Robots, Sensors");
  assert.equal(company.technologies, "Computer Vision, AI");
  assert.equal(company.summary, "N/A");
  assert.equal(company.score, 0.77);
});

test("sortCompaniesByScore orders results descending", () => {
  const sorted = sortCompaniesByScore([
    { company_name: "B", score: 0.3 },
    { company_name: "A", score: 0.9 },
    { company_name: "C", score: 0.5 },
  ]);

  assert.deepEqual(
    sorted.map((company) => company.company_name),
    ["A", "C", "B"]
  );
});

test("filterCompaniesByName matches company names only", () => {
  const filtered = filterCompaniesByName(
    [
      { company_name: "VisionFlight" },
      { company_name: "SkyAI Robotics" },
      { company_name: "Meta" },
    ],
    "sky"
  );

  assert.deepEqual(
    filtered.map((company) => company.company_name),
    ["SkyAI Robotics"]
  );
});

test("calculateAverageScore returns zero for empty input and the mean otherwise", () => {
  assert.equal(calculateAverageScore([]), 0);
  assert.ok(
    Math.abs(calculateAverageScore([{ score: 0.2 }, { score: 0.4 }, { score: 0.6 }]) - 0.4)
      < 1e-9
  );
});

test("utility helpers handle missing and list values safely", () => {
  assert.equal(safeText("", "Fallback"), "Fallback");
  assert.equal(safeScore("bad-value"), 0);
  assert.equal(normalizeListValue(["AI", "", "Cloud"]), "AI, Cloud");
  assert.deepEqual(normalizeListItems(["CRM", "", "Desk"]), ["CRM", "Desk"]);
  assert.deepEqual(normalizeListItems("CRM, Desk"), ["CRM", "Desk"]);
  assert.deepEqual(normalizeProductObjects('[{"name":"CRM","specifications":"Lead management"}]'), [
    { name: "CRM", specifications: "Lead management" },
  ]);
});

test("buildDetailSections includes all detail labels", () => {
  const markup = buildDetailSections({
    products: "Robots",
    product_specifications: "IP67",
    technologies: "AI",
    price_range: "$$$",
    contact_email: "hello@example.com",
    phone: "111",
    address: "Earth",
    description: "Desc",
    summary: "Summary",
  });

  assert.match(markup, /Products/);
  assert.match(markup, /Product Specifications/);
  assert.match(markup, /Technologies/);
  assert.match(markup, /Summary/);
});

test("extractCompanyRecordsFromPayload supports the current API response shape", () => {
  const records = [{ company_name: "Acme" }];

  assert.deepEqual(extractCompanyRecordsFromPayload(records), records);
  assert.deepEqual(extractCompanyRecordsFromPayload({ data: records }), records);
  assert.deepEqual(extractCompanyRecordsFromPayload({ companies: records }), records);
  assert.deepEqual(extractCompanyRecordsFromPayload({ status: "accepted", data: [] }), []);
});

test("buildProductGrid renders product cards with specifications", () => {
  const company = {
    products_structured: [
      { name: "Zoho CRM", specifications: "Lead management" },
      { name: "Zoho Desk", specifications: "Ticket automation" },
    ],
  };

  const markup = buildProductGrid(company);
  assert.match(markup, /product-grid/);
  assert.match(markup, /Zoho CRM/);
  assert.match(markup, /Lead management/);
});

test("buildProductGrid shows N/A when products are empty", () => {
  const company = { product_items: [], product_spec_items: [] };
  const markup = buildProductGrid(company);
  assert.match(markup, /product-grid-empty/);
  assert.match(markup, /N\/A/);
});
