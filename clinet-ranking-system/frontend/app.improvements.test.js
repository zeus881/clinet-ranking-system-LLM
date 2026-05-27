/**
 * Frontend Product Display Improvements - Test Suite
 * Tests for new product parsing, specification splitting, and technology tag functions
 */

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  parseProductString,
  parseSpecifications,
  parseTechnologies,
  buildProductsSection,
  safeText,
} = require("./app.js");

// ============================================================================
// parseProductString Tests
// ============================================================================

test("parseProductString: parses comma-separated product and features", () => {
  const result = parseProductString("Advanced drone platform, 4K camera, autonomous flight");
  
  assert.equal(result.name, "Advanced drone platform");
  assert.deepEqual(result.features, ["4K camera", "autonomous flight"]);
});

test("parseProductString: parses semicolon-separated features", () => {
  const result = parseProductString("Enterprise Software; cloud-based; scalable; secure");
  
  assert.equal(result.name, "Enterprise Software");
  assert.deepEqual(result.features, ["cloud-based", "scalable", "secure"]);
});

test("parseProductString: parses 'and'-separated features", () => {
  const result = parseProductString("AI System and machine learning capabilities and real-time processing");
  
  assert.equal(result.name, "AI System");
  assert.deepEqual(result.features, ["machine learning capabilities", "real-time processing"]);
});

test("parseProductString: handles single product name with no features", () => {
  const result = parseProductString("Simple Product");
  
  assert.equal(result.name, "Simple Product");
  assert.deepEqual(result.features, []);
});

test("parseProductString: returns null for empty string", () => {
  const result = parseProductString("");
  assert.equal(result, null);
});

test("parseProductString: returns null for null input", () => {
  const result = parseProductString(null);
  assert.equal(result, null);
});

test("parseProductString: returns null for whitespace only", () => {
  const result = parseProductString("   ");
  assert.equal(result, null);
});

test("parseProductString: trims whitespace from all parts", () => {
  const result = parseProductString("  Product Name  ,  Feature 1  ,  Feature 2  ");
  
  assert.equal(result.name, "Product Name");
  assert.deepEqual(result.features, ["Feature 1", "Feature 2"]);
});

test("parseProductString: handles mixed delimiters", () => {
  const result = parseProductString("Main Product, feature one; feature two and feature three");
  
  assert.equal(result.name, "Main Product");
  assert.deepEqual(result.features, ["feature one", "feature two", "feature three"]);
});

// ============================================================================
// parseSpecifications Tests
// ============================================================================

test("parseSpecifications: splits comma-separated specs", () => {
  const result = parseSpecifications("Cloud-based, scalable, secure, enterprise-ready");
  
  assert.deepEqual(result, ["Cloud-based", "scalable", "secure", "enterprise-ready"]);
});

test("parseSpecifications: splits period-separated specs", () => {
  const result = parseSpecifications("Feature one. Feature two. Feature three");
  
  assert.deepEqual(result, ["Feature one", "Feature two", "Feature three"]);
});

test("parseSpecifications: splits semicolon-separated specs", () => {
  const result = parseSpecifications("Spec A; Spec B; Spec C");
  
  assert.deepEqual(result, ["Spec A", "Spec B", "Spec C"]);
});

test("parseSpecifications: limits to 8 specifications", () => {
  const longString = "Spec1, Spec2, Spec3, Spec4, Spec5, Spec6, Spec7, Spec8, Spec9, Spec10";
  const result = parseSpecifications(longString);
  
  assert.equal(result.length, 8);
  assert.deepEqual(result, ["Spec1", "Spec2", "Spec3", "Spec4", "Spec5", "Spec6", "Spec7", "Spec8"]);
});

test("parseSpecifications: returns empty array for null", () => {
  const result = parseSpecifications(null);
  assert.deepEqual(result, []);
});

test("parseSpecifications: returns empty array for empty string", () => {
  const result = parseSpecifications("");
  assert.deepEqual(result, []);
});

test("parseSpecifications: returns empty array for whitespace only", () => {
  const result = parseSpecifications("   ");
  assert.deepEqual(result, []);
});

test("parseSpecifications: trims whitespace from specs", () => {
  const result = parseSpecifications("  Spec One  ,  Spec Two  ,  Spec Three  ");
  
  assert.deepEqual(result, ["Spec One", "Spec Two", "Spec Three"]);
});

// ============================================================================
// parseTechnologies Tests
// ============================================================================

test("parseTechnologies: splits comma-separated technologies", () => {
  const result = parseTechnologies("Python, JavaScript, React, Node.js");
  
  assert.deepEqual(result, ["Python", "JavaScript", "React", "Node.js"]);
});

test("parseTechnologies: splits semicolon-separated technologies", () => {
  const result = parseTechnologies("AI; Machine Learning; Computer Vision");
  
  assert.deepEqual(result, ["AI", "Machine Learning", "Computer Vision"]);
});

test("parseTechnologies: splits 'and'-separated technologies", () => {
  const result = parseTechnologies("Docker and Kubernetes and PostgreSQL");
  
  assert.deepEqual(result, ["Docker", "Kubernetes", "PostgreSQL"]);
});

test("parseTechnologies: limits to 12 technologies", () => {
  const longString = "Tech1, Tech2, Tech3, Tech4, Tech5, Tech6, Tech7, Tech8, Tech9, Tech10, Tech11, Tech12, Tech13";
  const result = parseTechnologies(longString);
  
  assert.equal(result.length, 12);
});

test("parseTechnologies: returns empty array for null", () => {
  const result = parseTechnologies(null);
  assert.deepEqual(result, []);
});

test("parseTechnologies: returns empty array for empty string", () => {
  const result = parseTechnologies("");
  assert.deepEqual(result, []);
});

test("parseTechnologies: handles case-insensitive 'and' separator", () => {
  const result = parseTechnologies("Python AND JavaScript and TypeScript");
  
  assert.deepEqual(result, ["Python", "JavaScript", "TypeScript"]);
});

// ============================================================================
// buildProductsSection Tests
// ============================================================================

test("buildProductsSection: renders products from strings", () => {
  const html = buildProductsSection(
    ["Advanced Platform, 4K Camera, Autonomous"],
    "",
    ""
  );
  
  assert(html.includes("Products"));
  assert(html.includes("Advanced Platform"));
  assert(html.includes("4K Camera"));
  assert(html.includes("Autonomous"));
  assert(html.includes("product-card"));
});

test("buildProductsSection: renders products from objects", () => {
  const html = buildProductsSection(
    [{ name: "Enterprise Solution", features: ["Cloud", "Scalable"] }],
    "",
    ""
  );
  
  assert(html.includes("Enterprise Solution"));
  assert(html.includes("Cloud"));
  assert(html.includes("Scalable"));
});

test("buildProductsSection: renders specifications as bullet list", () => {
  const html = buildProductsSection(
    [],
    "Cloud-based, Scalable, Secure",
    ""
  );
  
  assert(html.includes("Specifications"));
  assert(html.includes("Cloud-based"));
  assert(html.includes("Scalable"));
  assert(html.includes("Secure"));
  assert(html.includes("<ul"));
});

test("buildProductsSection: renders technologies as tags", () => {
  const html = buildProductsSection(
    [],
    "",
    "AI, Machine Learning, Python"
  );
  
  assert(html.includes("Technologies"));
  assert(html.includes("tech-tag"));
  assert(html.includes("AI"));
  assert(html.includes("Machine Learning"));
  assert(html.includes("Python"));
});

test("buildProductsSection: renders all three sections", () => {
  const html = buildProductsSection(
    ["Product Name, Feature 1, Feature 2"],
    "Spec 1, Spec 2",
    "Tech1, Tech2"
  );
  
  assert(html.includes("Products"));
  assert(html.includes("Specifications"));
  assert(html.includes("Technologies"));
});

test("buildProductsSection: shows fallback message when no data", () => {
  const html = buildProductsSection([], "", "");
  
  assert(html.includes("Product information not available"));
});

test("buildProductsSection: handles mixed product formats", () => {
  const html = buildProductsSection(
    [
      "String Product, Feature 1",
      { name: "Object Product", features: ["Feature A"] }
    ],
    "",
    ""
  );
  
  assert(html.includes("String Product"));
  assert(html.includes("Object Product"));
  assert(html.includes("Feature 1"));
  assert(html.includes("Feature A"));
});

test("buildProductsSection: handles null/undefined gracefully", () => {
  const html = buildProductsSection(null, null, null);
  assert(html.includes("Product information not available"));
});

test("buildProductsSection: hides empty sections", () => {
  const html = buildProductsSection(
    ["Product Name, Feature"],
    "",
    ""
  );
  
  // Should include Products and Product Name
  assert(html.includes("Products"));
  assert(html.includes("Product Name"));
  
  // Should not include empty Specifications or Technologies sections
  assert(!html.includes("Specifications"));
  assert(!html.includes("Technologies"));
});

test("buildProductsSection: creates proper HTML structure for products", () => {
  const html = buildProductsSection(
    ["Platform, Secure, Scalable"],
    "",
    ""
  );
  
  // Check for proper HTML elements
  assert(html.includes("<div class=\"products-section\">"));
  assert(html.includes("<div class=\"product-grid\">"));
  assert(html.includes("<div class=\"product-card\">"));
  assert(html.includes("<p class=\"product-card__name\">"));
  assert(html.includes("<ul class=\"product-card__features\">"));
  assert(html.includes("<li>"));
});

test("buildProductsSection: creates proper HTML structure for specifications", () => {
  const html = buildProductsSection(
    [],
    "Cloud, Secure, API Support",
    ""
  );
  
  assert(html.includes("<div class=\"specifications-section\">"));
  assert(html.includes("<ul class=\"specifications-list\">"));
  assert(html.includes("<li>Cloud</li>"));
});

test("buildProductsSection: creates proper HTML structure for technologies", () => {
  const html = buildProductsSection(
    [],
    "",
    "Python, JavaScript, Docker"
  );
  
  assert(html.includes("<div class=\"technologies-section\">"));
  assert(html.includes("<div class=\"tech-tags-container\">"));
  assert(html.includes("<span class=\"tech-tag\">Python</span>"));
});

// ============================================================================
// Integration Tests
// ============================================================================

test("Integration: Complex company profile with all data types", () => {
  const html = buildProductsSection(
    [
      "Enterprise Drone Platform, 4K Camera, 60 min Flight Time",
      { name: "Cloud Dashboard", features: ["Real-time Analytics", "Team Collaboration"] },
      "Mobile App, iOS Support, Android Support, Offline Mode"
    ],
    "Enterprise-grade security, Cloud-hosted infrastructure, 99.9% uptime SLA, API access, Unlimited users",
    "Python, TensorFlow, Computer Vision, React, PostgreSQL, Docker, AWS"
  );
  
  // Verify all products are rendered
  assert(html.includes("Enterprise Drone Platform"));
  assert(html.includes("4K Camera"));
  assert(html.includes("Cloud Dashboard"));
  assert(html.includes("Mobile App"));
  
  // Verify specifications are rendered
  assert(html.includes("Enterprise-grade security"));
  assert(html.includes("99.9% uptime SLA"));
  
  // Verify technologies are rendered
  assert(html.includes("Python"));
  assert(html.includes("TensorFlow"));
  assert(html.includes("AWS"));
  
  // Verify structure is correct
  assert(html.includes("Products"));
  assert(html.includes("Specifications"));
  assert(html.includes("Technologies"));
});

test("Integration: Real-world messy data is handled gracefully", () => {
  const html = buildProductsSection(
    [
      "  Messy Product  ,  Feature with extra spaces  ,  Another feature  ",
      null,
      undefined,
      ""
    ],
    "  Spec with spaces  .  Another Spec  .  Last Spec  ",
    "  Tech One  ;  Tech Two  and  Tech Three  "
  );
  
  // Should handle spaces and empty values
  assert(html.includes("Messy Product"));
  assert(html.includes("Feature with extra spaces"));
  assert(html.includes("Products"));
  assert(!html.includes("null"));
  assert(!html.includes("undefined"));
});

console.log("✅ All product display improvement tests passed!");
