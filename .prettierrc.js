/** @type {import("prettier").Config} */
module.exports = {
  overrides: [
    {
      files: "./**/*.json",
      options: {
        plugins: [require.resolve("prettier-plugin-sort-json")],
        jsonRecursiveSort: true,
        jsonSortOrder: JSON.stringify({ [/.*/]: "numeric" }),
      },
    },
  ],
};
