import { createDatabaseClient, createSiteContext, errorResponse, BackendError } from './_qoder/backend.mjs';
import { application } from './routes.mjs';

const handle = application({
  db: createDatabaseClient(),
  env: (name: string) => Deno.env.get(name),
  fetch: globalThis.fetch.bind(globalThis),
  BackendError,
});

Deno.serve(async (request: Request) => {
  let context;
  try {
    context = createSiteContext(request);
    return await handle(context);
  } catch (error) {
    return errorResponse(error, context?.requestId);
  }
});