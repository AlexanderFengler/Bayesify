import { Box, Container, type ContainerProps } from "@mui/material";

// The hero content shell for the full-bleed screens (cover, landing, analyzing). The dynamic aurora
// is global now (rendered by Layout behind everything), so this shell is transparent — it only
// centers its content, both axes, within the routed area so the centerpiece sits in the middle of
// the page. `maxWidth` widens the content column per screen (landing runs wider than the rest).
export function HeroShell({
  children,
  maxWidth = "lg",
}: {
  children: React.ReactNode;
  maxWidth?: ContainerProps["maxWidth"];
}) {
  return (
    <Box
      sx={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center", // vertically center the centerpiece in the page
        color: "text.primary",
      }}
    >
      <Container maxWidth={maxWidth} sx={{ py: { xs: 4, md: 6 } }}>
        {children}
      </Container>
    </Box>
  );
}
