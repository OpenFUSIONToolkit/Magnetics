// The "stop the analysis at the Ip flattop end" option (store.cutFlattop): every
// analysis fetch carries `cut_flattop=1` when it's on, and the backend ends the QS fit
// window, the rotating tracks and the (t, f) maps at the flattop end it finds from Ip.

type Params = Record<string, string | number>;

/** `params` with `cut_flattop` set when `on`, and removed when not (params published
 *  by another tab may already carry it). */
export function withFlattopCut<P extends Params>(params: P, on: boolean): P {
  const { cut_flattop: _drop, ...rest } = params; // eslint-disable-line @typescript-eslint/no-unused-vars
  return (on ? { ...rest, cut_flattop: 1 } : rest) as unknown as P;
}
