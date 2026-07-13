// Trimmed from hexsheet's signal.types.ts to just the members hex-flower.ts
// and dice-pool.ts use directly. hex-flower is embedded standalone here (no
// hex-sheet container listens for these events), so they're dispatched but
// never connected -- kept so the dispatch code ports over unchanged.

// Called by signal-container to give the sender its send and disconnect callbacks.
export type SignalConnectCallback = (
  send: (message: string) => void,
  disconnect: () => void,
) => void;

export interface RegisterSignalSenderDetail {
  sheetItemId: string;
  signalId: string;
  connect: SignalConnectCallback;
}

export interface RegisterDatastoreDetail {
  sheetItemId: string;
  serializeData: () => string;
  loadFromSerializedData: (data: string) => void;
  disconnect: () => void; // called by the container when the item is removed
}
