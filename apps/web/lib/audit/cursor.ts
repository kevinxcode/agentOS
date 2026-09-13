export const MAX_CURSOR_TRAIL = 50;
const MAX_CURSOR_LENGTH = 512;

export type CursorTrail = Array<string | null>;

export function parseCursorTrail(raw: string | null | undefined): CursorTrail {
  if (!raw) return [];
  try {
    const value: unknown = JSON.parse(raw);
    if (
      !Array.isArray(value) ||
      value.length > MAX_CURSOR_TRAIL ||
      !value.every(
        (cursor) =>
          cursor === null ||
          (typeof cursor === "string" && cursor.length > 0 && cursor.length <= MAX_CURSOR_LENGTH),
      )
    ) {
      return [];
    }
    return value as CursorTrail;
  } catch {
    return [];
  }
}

export function serializeCursorTrail(trail: CursorTrail): string {
  return JSON.stringify(trail.slice(-MAX_CURSOR_TRAIL));
}
