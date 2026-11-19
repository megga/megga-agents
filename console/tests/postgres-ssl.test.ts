import { describe, expect, it } from "vitest";
import { normaliserSsl } from "@/lib/donnees/postgres";

describe("normaliserSsl", () => {
  it.each(["require", "prefer", "verify-ca"])("sslmode=%s devient verify-full", (mode) => {
    expect(normaliserSsl(`postgres://u:p@h/db?sslmode=${mode}`)).toBe("postgres://u:p@h/db?sslmode=verify-full");
    expect(normaliserSsl(`postgres://u:p@h/db?a=1&sslmode=${mode}&b=2`)).toBe("postgres://u:p@h/db?a=1&sslmode=verify-full&b=2");
  });

  it("laisse le reste tel quel", () => {
    for (const u of ["postgres://u:p@h/db", "postgres://u:p@h/db?sslmode=verify-full", "postgres://u:p@h/db?sslmode=disable", "postgres://u:p@h/db?x=sslmode=require"]) {
      expect(normaliserSsl(u)).toBe(u);
    }
  });
});
