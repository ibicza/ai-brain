# M-27.1 Conflict Resolution Policy

Fact conflict policy `4.0` requires a complete reviewed partition. For manual
resolution every retained claim needs approved `SUPPORTS_REMAINING` evidence and
every removed claim needs distinct approved `CONTRADICTS_REMOVED` evidence
attached to that claim. Winner support alone cannot remove a competitor.

Links must cover the declared evidence set, preserve immutable polarity, belong
to the conflict domain and predate the resolution event. Selected and remaining
claims must be group members; manual selected equals remaining and the removed
set is exactly the group complement.

`DISMISSED_AS_NOT_CONFLICTING` removes nothing. It must select and retain the
entire group and bind `SUPPORTS_DISMISSAL` evidence to every claim. There is no
free-text dismissal bypass and no autonomous winner.

