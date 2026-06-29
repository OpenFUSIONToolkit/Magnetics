// plotly.js-dist-min ships no types; reuse the @types/plotly.js declarations.
declare module "plotly.js-dist-min" {
  import * as Plotly from "plotly.js";
  export = Plotly;
}
