import { describe, expect, it } from 'vitest';
import {
  ApiRequestError,
  apiUrl,
  readJson,
  resolveApiBase,
} from '../lib/api';

describe('resolveApiBase', () => {
  it('defaults to the local backend when unset or blank', () => {
    expect(resolveApiBase(undefined)).toBe('http://localhost:8000');
    expect(resolveApiBase('')).toBe('http://localhost:8000');
    expect(resolveApiBase('   ')).toBe('http://localhost:8000');
  });

  it('strips trailing slashes from configured bases', () => {
    expect(resolveApiBase('https://api.example.com/')).toBe('https://api.example.com');
    expect(resolveApiBase('https://api.example.com///')).toBe('https://api.example.com');
  });
});

describe('apiUrl', () => {
  it('joins base and path with exactly one slash', () => {
    expect(apiUrl('/ask')).toBe('http://localhost:8000/ask');
    expect(apiUrl('ask')).toBe('http://localhost:8000/ask');
  });
});

describe('readJson', () => {
  it('returns the parsed body on success', async () => {
    const res = new Response(JSON.stringify({ answer: '42' }), { status: 200 });
    await expect(readJson(res)).resolves.toEqual({ answer: '42' });
  });

  it('returns null for an empty success body', async () => {
    const res = new Response('', { status: 200 });
    await expect(readJson(res)).resolves.toBeNull();
  });

  it('throws the server detail on a JSON error response', async () => {
    const res = new Response(JSON.stringify({ detail: "Field 'question' is required." }), {
      status: 400,
    });
    await expect(readJson(res)).rejects.toThrowError(
      new ApiRequestError("Field 'question' is required.", 400)
    );
  });

  it('falls back to the raw body text on a non-JSON error response', async () => {
    const res = new Response('<html>Bad Gateway</html>', { status: 502 });
    const err = await readJson(res).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiRequestError);
    expect((err as ApiRequestError).message).toBe('<html>Bad Gateway</html>');
    expect((err as ApiRequestError).status).toBe(502);
  });

  it('falls back to statusText when the error body is empty', async () => {
    const res = new Response('', { status: 500, statusText: 'Internal Server Error' });
    const err = await readJson(res).catch((e: unknown) => e);
    expect((err as ApiRequestError).message).toBe('Internal Server Error');
    expect((err as ApiRequestError).status).toBe(500);
  });
});
