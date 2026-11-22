// Build stamp for the hosted desk Function. The committed copy is deliberately blank:
// `scripts/stamp_desk_build.py write` fills it from git immediately before a publish, after
// refusing any tree that is not a clean checkout of origin/main, and `--restore` blanks it
// again afterwards. The health route (`/app`, `/health`) reports it, so the signed-in
// acceptance read also answers "does the live site run main, and which commit?".
export const BUILD = {
  sha: "unstamped",
  branch: "",
  dirty: null as boolean | null,
  stamped_at: null as string | null,
};
