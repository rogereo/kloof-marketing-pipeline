CREATE OR REPLACE MODEL
  `kloof-marketing-pipeline.kloof_silver.gemini_creative_model`
REMOTE WITH CONNECTION
  `kloof-marketing-pipeline.us.kloof_vertex_ai`
OPTIONS (
  ENDPOINT = 'gemini-3.1-flash-lite'
);
