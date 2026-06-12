export {}

declare module '*.svg' {
  const content: string
  export default content
}

declare module '*.json' {
  const value: unknown
  export default value
}