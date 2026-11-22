// Norgine's adoption ladder, as the brand team uses it, against the engine's journey stages.
export const LADDER_LABEL = { unaware: "Unaware", aware: "Aware", occasional: "Occasional use", regular: "Regular use", advocate: "Advocate" };
export const STAGE_TO_LADDER = { curiosity: "unaware", consideration: "aware", experience: "occasional", loyalty: "regular", advocacy: "advocate" };
export const ladderOf = (stage) => LADDER_LABEL[STAGE_TO_LADDER[stage]] || stage;
// The segmentation's adoption bands in ladder words.
export const BAND_LADDER = { early: "Unaware or aware", building: "Occasional use", established: "Regular use or advocate" };
