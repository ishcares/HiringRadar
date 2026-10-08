/**
 * HiringRadar AI Microservice - Cloudflare Workers AI
 * Models:
 * - Embedding: @cf/qwen/qwen3-embedding-0.6b
 * - Reranker:  @cf/baai/bge-reranker-base
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // CORS Headers
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // Optional Secret Token Check
    if (env.AUTH_SECRET) {
      const auth = request.headers.get("Authorization");
      if (!auth || auth !== `Bearer ${env.AUTH_SECRET}`) {
        return new Response(JSON.stringify({ error: "Unauthorized" }), {
          status: 401,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
    }

    // Health check
    if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/health")) {
      return new Response(
        JSON.stringify({
          status: "online",
          service: "HiringRadar Workers AI",
          embedding_model: "@cf/qwen/qwen3-embedding-0.6b",
          reranker_model: "@cf/baai/bge-reranker-base",
        }),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    // POST /embed -> Generate Qwen3-0.6B Embeddings
    if (request.method === "POST" && url.pathname === "/embed") {
      try {
        const body = await request.json();
        const texts = body.texts || (body.text ? (Array.isArray(body.text) ? body.text : [body.text]) : []);

        if (!texts.length) {
          return new Response(JSON.stringify({ error: "Missing 'texts' in request body" }), {
            status: 400,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          });
        }

        const aiResponse = await env.AI.run("@cf/qwen/qwen3-embedding-0.6b", {
          text: texts,
        });

        const embeddings = aiResponse.data || aiResponse;
        return new Response(
          JSON.stringify({ success: true, embeddings }),
          {
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      } catch (err) {
        return new Response(
          JSON.stringify({ error: "Embedding failed", details: String(err) }),
          {
            status: 500,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      }
    }

    // POST /rerank -> Run BAAI Cross-Encoder Reranker
    if (request.method === "POST" && url.pathname === "/rerank") {
      try {
        const body = await request.json();
        const { query, contexts } = body;

        if (!query || !contexts || !Array.isArray(contexts) || contexts.length === 0) {
          return new Response(
            JSON.stringify({ error: "Missing 'query' string or 'contexts' array" }),
            {
              status: 400,
              headers: { ...corsHeaders, "Content-Type": "application/json" },
            }
          );
        }

        const aiResponse = await env.AI.run("@cf/baai/bge-reranker-base", {
          query,
          contexts,
        });

        return new Response(
          JSON.stringify({ success: true, results: aiResponse.results || aiResponse }),
          {
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      } catch (err) {
        return new Response(
          JSON.stringify({ error: "Reranker failed", details: String(err) }),
          {
            status: 500,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          }
        );
      }
    }

    return new Response(JSON.stringify({ error: "Not found" }), {
      status: 404,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  },
};
