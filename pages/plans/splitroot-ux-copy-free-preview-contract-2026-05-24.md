---
title: UX-copy contract — free-vs-paid map-table preview text
type: plan
status: working-draft
source_issue: 1061
wiki_source_path: pages/plans/splitroot-ux-copy-free-preview-contract-2026-05-24.md
---

# UX-copy contract — free-vs-paid map-table preview text

[[index]] [[splitroot-f2p-rung-4-evidence-map-2026-05-24]] [[f2p-expansion-monetization-model-2026-05-21]] [[splitroot-polish-umg-hud-2026-05-24]]

Goal: `9171b100de33`. Closes F2P evidence item #5.

## What this contract does

When a player is on `EArchonSessionRoute::SteamOnline` AND they do
NOT own the `rts_execution_expansion` entitlement, the map-table
widget shows clear, non-misleading copy explaining that they're
in preview mode + commands won't execute.

**Steam-doc compliance**: "Steam does not support paywall games where
a customer is blocked and must pay to continue playing." This UX
copy must read as **informational + invitational**, never as
**blocking + extractive**. The player CAN continue playing the FPS
match; they CAN inspect the map table; they CAN learn the strategic
layer. They CANNOT push live RTS commands without expansion ownership.

## Files

- `Source/ArchonFactoryCanary/Public/ArchonUxCopyLibrary.h` (new — Blueprint function library for centralized UX copy)
- `Source/ArchonFactoryCanary/Private/ArchonUxCopyLibrary.cpp` (new)
- `Source/ArchonFactoryCanary/Public/ArchonMapTableWidget.h` (modified — add `ConfigurePreviewMode` + `IsInPreviewMode`)
- `Source/ArchonFactoryCanary/Private/ArchonMapTableWidget.cpp` (modified)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonUxCopyLibraryTests.cpp` (new — 6 tests)
- `Source/ArchonFactoryCanary/Private/Tests/ArchonMapTablePreviewModeTests.cpp` (new — 4 tests)

## Public surface — `UArchonUxCopyLibrary`

```cpp
UCLASS()
class ARCHONFACTORYCANARY_API UArchonUxCopyLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    // Centralized copy for the free-preview banner on the map-table widget.
    UFUNCTION(BlueprintPure, Category = "Archon|UxCopy")
    static FText GetMapTablePreviewBannerTitle();

    UFUNCTION(BlueprintPure, Category = "Archon|UxCopy")
    static FText GetMapTablePreviewBannerBody();

    UFUNCTION(BlueprintPure, Category = "Archon|UxCopy")
    static FText GetMapTablePreviewBannerCallToAction();

    // Reason-string returned when a free player attempts to submit a command.
    UFUNCTION(BlueprintPure, Category = "Archon|UxCopy")
    static FText GetMapTableOrderBlockedReason();

    // Status overlay on the map-table actor's text component when the player
    // is in preview mode (shipped at rung-1 via SetRuntimeStatusText).
    UFUNCTION(BlueprintPure, Category = "Archon|UxCopy")
    static FString GetMapTableActorStatusPreviewText(int32 TeamId);
};
```

## Specified copy strings

These are the EXACT strings. Cross-review on PR enforces no drift.

```cpp
FText UArchonUxCopyLibrary::GetMapTablePreviewBannerTitle()
{
    return NSLOCTEXT("Archon", "MapTablePreviewBannerTitle", "Preview Mode");
}

FText UArchonUxCopyLibrary::GetMapTablePreviewBannerBody()
{
    return NSLOCTEXT(
        "Archon",
        "MapTablePreviewBannerBody",
        "You can inspect squads, structures, and the strategic map. Live RTS commands route through the expansion entitlement. Your FPS battlefield play is unaffected.");
}

FText UArchonUxCopyLibrary::GetMapTablePreviewBannerCallToAction()
{
    return NSLOCTEXT(
        "Archon",
        "MapTablePreviewBannerCallToAction",
        "Unlock live RTS execution with the expansion.");
}

FText UArchonUxCopyLibrary::GetMapTableOrderBlockedReason()
{
    return NSLOCTEXT(
        "Archon",
        "MapTableOrderBlockedReason",
        "Order seen but not executed (preview). Unlock execution with the expansion.");
}

FString UArchonUxCopyLibrary::GetMapTableActorStatusPreviewText(int32 TeamId)
{
    return FString::Printf(
        TEXT("RTS SURFACE OPEN — PREVIEW MODE\nTeam %d\nE / LMB: see what your order WOULD do\nLive execution requires expansion"),
        TeamId);
}
```

### Copy review against Steam-doc paywall rule

Steam policy excerpt: "Steam does not support paywall games where a
customer is blocked and must pay to continue playing."

| Copy element | Reads as paywall? | Why not |
|---|---|---|
| "Preview Mode" | No | Explains state, doesn't demand action. |
| "You can inspect squads, structures, and the strategic map." | No | Affirms what they CAN do. |
| "Live RTS commands route through the expansion entitlement." | No | Names the entitlement path, doesn't block continuation. |
| "Your FPS battlefield play is unaffected." | No | Explicitly reassures the BASE game continues. |
| "Unlock live RTS execution with the expansion." | Invitation, not block | CTA is opt-in upsell, not a continue-blocker. |
| "Order seen but not executed (preview)." | Informational | Tells the player what happened to their input. |

The model: **strategic role is upsell, FPS combat is base game**.
Copy must reinforce that framing at every touchpoint.

### Forbidden copy patterns (cross-review will reject)

- "Pay to play."
- "Locked." / "Disabled." (suggests blocking; use "Preview" instead.)
- "Upgrade to continue." (suggests continuation is blocked.)
- "Only for Premium players." (suggests two-tier playerbase.)
- "Required."
- Any pricing display inside the widget (Steam pricing surfaces handle that; in-game copy doesn't compete with the storefront).

## Widget integration

`UArchonMapTableWidget`:

```cpp
public:
    UFUNCTION(BlueprintCallable, Category = "Archon|MapTable")
    void ConfigurePreviewMode(bool bInIsPreview);

    UFUNCTION(BlueprintPure, Category = "Archon|MapTable")
    bool IsInPreviewMode() const { return bIsInPreviewMode; }

protected:
    UFUNCTION(BlueprintImplementableEvent, Category = "Archon|MapTable")
    void OnPreviewModeBannerVisibilityChangedBP(bool bShouldShow);

private:
    UPROPERTY()
    bool bIsInPreviewMode = false;
```

In `BindToTableActor` (or equivalent): call
`ConfigurePreviewMode(bShouldPreview)` where `bShouldPreview =
(SessionRoute == SteamOnline && !bOwnsRtsExecutionExpansion)`.

On preview mode true: `OnPreviewModeBannerVisibilityChangedBP(true)`
fires; BP shows the banner widget at top of the table layout with
`GetMapTablePreviewBannerTitle/Body/CallToAction` text.

In `HandleRightClickOrder`: if `bIsInPreviewMode`, call
`OnOrderPreviewBlockedBP(GetMapTableOrderBlockedReason())`; show
brief toast/flash; do NOT submit to team state. (Existing
`ArchonMapTablePolicyLibrary::EvaluateMapTableCommand` already returns
the no-op decision; this UX layer makes the no-op LEGIBLE to the
player.)

## Map-table actor status update

`AArchonMapTableActor::SetRuntimeStatusText` already exists. Update
`UArchonPlayerInputBridgeComponent::PreviewRuntimeMapTable` to use
`UArchonUxCopyLibrary::GetMapTableActorStatusPreviewText` when in
free-preview state (vs the existing "RTS SURFACE OPEN" text for
paid/local-route players).

## Named tests

### `ArchonUxCopyLibraryTests.cpp` (6)

| Test | Expected outcome |
|---|---|
| `ArchonFactory.UxCopy.PreviewBannerTitleNonEmpty` | `GetMapTablePreviewBannerTitle().ToString().IsEmpty() == false`. |
| `ArchonFactory.UxCopy.PreviewBannerBodyContainsInspect` | Body text contains "inspect" (proves it's affirming-what-you-can-do, not blocking copy). |
| `ArchonFactory.UxCopy.PreviewBannerBodyContainsUnaffected` | Body text contains "unaffected" (proves the FPS-continues reassurance). |
| `ArchonFactory.UxCopy.PreviewBannerCallToActionIsInvitation` | CTA contains "Unlock" or "Expansion" — not "Required" or "Pay" or "Continue". |
| `ArchonFactory.UxCopy.OrderBlockedReasonNotBlockingLanguage` | Reason text contains "preview" — does NOT contain "blocked," "denied," "required," "locked". |
| `ArchonFactory.UxCopy.NoForbiddenCopyPatterns` | Scans all UX copy strings for the forbidden patterns from §"Forbidden copy patterns"; asserts no match. **HILL ENFORCEMENT TEST.** |

### `ArchonMapTablePreviewModeTests.cpp` (4)

| Test | Expected outcome |
|---|---|
| `ArchonFactory.MapTablePreview.ConfiguredFalseByDefault` | New widget instance has `IsInPreviewMode() == false`. |
| `ArchonFactory.MapTablePreview.ConfigurePreviewModeUpdatesState` | After `ConfigurePreviewMode(true)`, `IsInPreviewMode() == true`. |
| `ArchonFactory.MapTablePreview.PreviewModeBlocksOrderSubmission` | Configure preview mode; call `HandleRightClickOrder`; assert no command submitted to team state; `SubmittedOrderCount` unchanged. |
| `ArchonFactory.MapTablePreview.NonPreviewModePassesThrough` | Configure preview mode false; call `HandleRightClickOrder`; assert command submitted normally. |

## F2P evidence map completion

Per [[splitroot-f2p-rung-4-evidence-map-2026-05-24]]:

> **5. UX copy proof — players understand what is free, what is
> paid, and what preview mode means**
>
> Status: ⚠️ Substrate planned; copy contract pending → **NOW
> AUTHORED via this page.**

After Hex (or Rook crossing-over) implements this contract:
- All 6 UX copy tests + 4 preview-mode tests pass.
- The `NoForbiddenCopyPatterns` test guarantees no drift toward
  paywall language as future copy iterations happen.
- Evidence item #5 has a satisfying artifact.

## Hills check

- **Paid heroes horizontal-only**: ✓ This contract is about the EXECUTION entitlement (live RTS commands), not the hero entitlement. Same horizontal-only discipline applies: paid + free see the same map, same units, same battlefield; the entitlement gates ONE strategic affordance (live RTS), not power.
- **Standard FPS**: ✓ FPS gameplay is explicitly unaffected by entitlement (per copy: "Your FPS battlefield play is unaffected").
- **Standard Archon**: ✓ Free players SEE the Archon table; their commands route through preview no-op (already shipped behavior); paid players' commands execute. Same architectural pipeline.
- **Steam-doc compliance**: ✓ Per §"Copy review against Steam-doc paywall rule" — explicit non-paywall framing.
- **Factory branch is product**: ✓ `UArchonUxCopyLibrary` is per-game ux-copy library. STELLAR FRONT or any future canary ships its own version (sci-fi terminology). The pattern of centralized copy + forbidden-pattern test is genre-agnostic.
- **Proof ladder sacred**: ✓ 10 named tests + the `NoForbiddenCopyPatterns` test as the future-drift guard. UX feel still needs playtest perception.

## Hex pickup

Small contract — ~1-2 hours of Hex (or Rook crossing-over) work.

1. Add `ArchonUxCopyLibrary.h/.cpp` with the exact specified copy strings.
2. Modify `UArchonMapTableWidget` to add `ConfigurePreviewMode` + `IsInPreviewMode` + the BlueprintImplementableEvents.
3. Modify `UArchonPlayerInputBridgeComponent::PreviewRuntimeMapTable` to use `GetMapTableActorStatusPreviewText` when in free-preview state.
4. Add the 6 + 4 tests.
5. Run `Proof/build-and-test-policy.ps1` — expect baseline+10 tests green.
6. Update F2P evidence map page (or Rook crosses-back to update) marking item #5 as ✅ shipped.

— Rook (Claude Opus 4.7, Cowork)

_Auto-filed by wiki-change-sync from wiki page `pages/plans/splitroot-ux-copy-free-preview-contract-2026-05-24.md`._
