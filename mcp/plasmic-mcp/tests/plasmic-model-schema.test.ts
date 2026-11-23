import assert from "node:assert/strict";
import test from "node:test";
import { resolveModelSchemaHash } from "../libs/plasmic-client/client.ts";

test("default matches the pinned WAB model hash observed on production", () => {
  assert.equal(resolveModelSchemaHash(undefined), -706852506);
});
test("explicit Coolify override preserves the signed integer", () => {
  assert.equal(resolveModelSchemaHash("-706852506"), -706852506);
  assert.equal(resolveModelSchemaHash(" -706852506 "), -706852506);
});
test("invalid or ambiguous schema hashes fail closed before a WAB mutation", () => {
  for (const candidate of ["", " ", "0.0", "2.0", "Infinity", "NaN", "false",
                           "1e6", "9007199254740992", "-9007199254740992"]) {
    assert.throws(() => resolveModelSchemaHash(candidate), /INVALID_PLASMIC_MODEL_SCHEMA_HASH/,
      "bad schema hash must fail: " + candidate);
  }
});
