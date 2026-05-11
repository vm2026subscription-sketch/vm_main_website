CREATE TABLE editions (
  id SERIAL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  publish_date DATE NOT NULL UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pages (
  id SERIAL PRIMARY KEY,
  edition_id INTEGER NOT NULL REFERENCES editions(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  image_path TEXT NOT NULL,
  layout_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (edition_id, page_number)
);

CREATE TABLE articles (
  id SERIAL PRIMARY KEY,
  title VARCHAR(255) NOT NULL,
  slug VARCHAR(255) UNIQUE,
  content TEXT NOT NULL,
  author VARCHAR(160),
  category VARCHAR(120),
  image TEXT,
  publish_date DATE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pages_edition_id ON pages(edition_id);
CREATE INDEX idx_articles_category ON articles(category);
CREATE INDEX idx_articles_publish_date ON articles(publish_date);
