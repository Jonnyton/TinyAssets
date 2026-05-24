# Auto-Change Loop Diff Detection Fix

## Problem
The auto-change loop should detect when its own diff removes content, preventing infinite loops.

## Analysis
When a wiki bot applies changes and the change removes content, the bot's monitoring loop may detect the removal as a new change and attempt to restore it, creating an infinite loop.

## Solution: Self-Diff Detection

```python
class AutoChangeLoop:
    def __init__(self, bot_id: str):
        self.bot_id = bot_id
        self.last_applied_diffs = {}  # page_id -> last diff hash
    
    def detect_own_diff(self, page_id: str, diff: dict) -> bool:
        """Check if a diff was produced by this bot."""
        # Check 1: Diff author matches bot
        if diff.get('author') == self.bot_id:
            return True
        
        # Check 2: Diff content hash matches last applied
        diff_hash = hash_diff(diff)
        if self.last_applied_diffs.get(page_id) == diff_hash:
            return True
        
        return False
    
    def should_revert(self, page_id: str, diff: dict) -> bool:
        """Determine if a change should be reverted."""
        if self.detect_own_diff(page_id, diff):
            return False  # Don't revert own changes
        
        # Check if diff removes content added by bot
        if self.removes_bot_content(page_id, diff):
            return True
        
        return False
```

## Implementation Steps
1. Add `bot_id` to all edit summaries
2. Track last-applied diff hashes per page
3. Skip diffs authored by self
4. Add cooldown period after own edits (30 seconds)
5. Log all self-diff detections for debugging
