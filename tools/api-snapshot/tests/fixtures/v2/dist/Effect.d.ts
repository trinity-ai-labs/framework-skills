import type { LazyArg } from "./Function.ts";
/**
 * One-line const.
 * @since 2.0.0
 */
export declare const succeed: <A>(value: A, extra?: string) => A;
/**
 * Dual API: the inner signatures repeat the docs but are not exports.
 * @since 2.0.0
 */
export declare const mapRenamed: {
    /**
     * Data-last.
     * @since 2.0.0
     * @stability unstable
     */
    <A, B>(f: (a: A) => B): (self: A) => B;
    /**
     * Data-first.
     * @since 2.0.0
     */
    <A, B>(self: A, f: (a: A) => B): B;
};
/**
 * Overloads share the first doc comment.
 * @since 2.0.0
 */
export declare function gen<A>(f: () => A): A;
export declare function gen<A>(self: unknown, f: () => A): A;
/**
 * A type and a value share a name.
 * @since 2.0.0
 */
export interface Effect<A> {
    readonly _A: A;
}
/**
 * @since 2.0.0
 */
export declare const Effect: { readonly make: number };
/**
 * @since 2.0.0
 */
export declare namespace Effect {
    /**
     * @since 3.0.0
     */
    type Success<T> = T;
    /**
     * @since 3.0.0
     * @stability unstable
     */
    interface Services {
        readonly a: string;
    }
}
declare const Service_base: new () => {};
/**
 * @since 2.0.0
 */
export declare class Service extends Service_base {
    readonly tag: string;
}
declare const void_: Effect<void>;
export { 
/**
 * The reserved word `void`.
 * @since 2.0.0
 */
void_ as void };
/**
 * Doc whose example looks like declarations.
 *
 * @example
 * ```ts
 * export declare const fake: number;
 * export interface Fake {}
 * ```
 * @since 2.0.0
 */
/**
 * @since 4.1.0
 */
export declare const brandNew: number;
export declare const real: number;
/**
 * @since 4.0.0
 */
export type Tagged = string;
export {};
