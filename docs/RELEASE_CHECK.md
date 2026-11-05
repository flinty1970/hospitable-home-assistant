# Release and installation check

Checked 5 November 2026 as a documentation-only review. No release was created or
changed, and no tags, branches or Git history were rewritten.

## Existing release

The published [v0.1.2 release](https://github.com/flinty1970/hospitable-home-assistant/releases/tag/v0.1.2)
exists, is not a draft or prerelease, and has a matching lightweight Git tag.
The tag resolves to commit `af3a77b8cc7e094d76bf05d2e2f6e03a143b65a8`.
The release API's `targetCommitish` is `main`; the tag's actual commit was checked
separately rather than assuming that it follows the latest main branch.

| Check | Tagged release and current files |
|---|---|
| Manifest version | `0.1.2` |
| Domain | `hospitable_stays` |
| Documentation | `https://github.com/flinty1970/hospitable-home-assistant` |
| Issue tracker | `https://github.com/flinty1970/hospitable-home-assistant/issues` |
| HACS display name | Hospitable Stays |
| HACS minimum Home Assistant version | `2026.10.0` |
| README minimum Home Assistant version | `2026.10.0` |

The manifest does not have a separate minimum-HA field, and hacs.json does not have
a release-version field. Their distinct roles are consistent; no missing field
was invented. The test runtime is HA 2026.10.4. This review does not claim a new
runtime test on the exact minimum, 2026.10.0.

## Custom-repository installation

Verified against HACS's own documentation:

- [Custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/): enter
  the repository URL, choose the integration type and add it.
- [Downloading repositories](https://www.hacs.xyz/docs/use/repositories/dashboard/):
  open the repository and download it. The newest release is the default;
  a different version can be selected. A pending-restart status requires an HA restart.
- [Integration repositories](https://www.hacs.xyz/docs/use/repositories/type/integration/):
  integration files are placed beneath the HA configuration's custom_components
  directory. This integration then uses its UI config flow in Devices & services.

Adding the custom repository does not itself configure an account or install an
automation. The README keeps registration, downloading, any required restart,
and account setup as distinct steps. Default-catalogue inclusion is a separate process.
