import { render, screen } from "@testing-library/react";
import App from "../App";

test("renders keyword heading and brand", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: /twitter\/x video downloader/i })).toBeInTheDocument();
  expect(screen.getByText("SaveVid AI")).toBeInTheDocument();
});
